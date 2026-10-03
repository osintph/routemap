"""
Build the project site (getroutemap.app) into site/build/.

    python site/build.py [--tag v0.1.0-beta.4] [--release-json release.json]
                         [--sums SHA256SUMS] [--out DIR]

- Branding, links, contact and donations come from site/site.toml, so a rename
  or a domain change is one edit there.
- Page text comes from the repository's own documents wherever one exists
  (docs/*.md, PRIVACY.md, CODE_SIGNING_POLICY.md, CHANGELOG.md), so the site
  and the repository cannot drift apart. The rest is in site/content/.
- No external assets: fonts, images and the one small script are served from
  the site. Every page reads fully without JavaScript; the script only marks
  the visitor's platform so the matching download button comes first.
- Dependencies: the standard library and segno (QR codes for the donation
  addresses, drawn here from the address text; site/requirements.txt).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import pathlib
import re
import shutil
import sys
import tomllib

SITE = pathlib.Path(__file__).resolve().parent
ROOT = SITE.parent
OUT = SITE / "build"
sys.path.insert(0, str(ROOT))
from routemap.__about__ import __version__  # noqa: E402

CONFIG = tomllib.loads((SITE / "site.toml").read_text(encoding="utf-8"))
S, L, D = CONFIG["site"], CONFIG["links"], CONFIG["donate"]
SIGNED = CONFIG["signing"]["signpath_signed"]
ATTRIBUTION = CONFIG["signing"]["signpath_attribution"]
FPR = CONFIG["release"]["gpg_fingerprint"]
FPR_SPACED = " ".join(FPR[i:i + 4] for i in range(0, len(FPR), 4))
CURRENT = ' aria-current="page"'
LATEST = ""   # the release tag the site describes; set in main()

NAV = [("/download/", "Download"), ("/docs/", "Docs"), ("/screenshots/", "Screenshots"),
       ("/changelog/", "Changelog"), ("/support/", "Support"), ("/about/", "About")]

# Repository documents that have a page here; any other relative link goes to GitHub.
LOCAL_DOCS = {"PRIVACY.md": "/privacy/", "CODE_SIGNING_POLICY.md": "/code-signing/",
              "CHANGELOG.md": "/changelog/", "guide.md": "/docs/guide/", "cli.md": "/docs/cli/",
              "faq.md": "/docs/faq/", "limitations.md": "/docs/limitations/",
              "troubleshooting.md": "/docs/troubleshooting/", "RELEASE-KEY.asc": "/release-key.asc"}

PLATFORMS = [
    # key, label, file pattern, note
    ("windows", "Windows 10/11", "routemap-{v}-windows-x86_64.zip", "x86_64, zip"),
    ("macos", "macOS, Apple silicon", "routemap-{v}-macos-arm64.dmg", "macOS 12+, dmg"),
    ("macos-intel", "macOS, Intel", "routemap-{v}-macos-x86_64.dmg", "macOS 12+, dmg"),
    ("linux", "Linux AppImage", "routemap-{v}-linux-x86_64.AppImage", "x86_64"),
    ("linux-tar", "Linux tar.gz", "routemap-{v}-linux-x86_64.tar.gz", "x86_64"),
]


# ------------------------------------------------------------------ markdown ---
# The subset the project's documents use: headings, paragraphs, lists, tables,
# fenced code, block quotes, and inline code, bold, italics and links.

def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", text).lower()).strip("-")


def _link(url: str) -> str:
    base, _, anchor = url.partition("#")
    name = base.rsplit("/", 1)[-1]
    if name in LOCAL_DOCS:
        return LOCAL_DOCS[name] + (f"#{anchor}" if anchor else "")
    if base and not re.match(r"^[a-z]+:|^/|^#", base):
        return f"{L['repository']}/blob/main/{base.lstrip('./')}" + (f"#{anchor}" if anchor else "")
    return url


def inline(text: str) -> str:
    out = []
    for part in re.split(r"(`[^`]+`)", text):
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(f"<code>{html.escape(part[1:-1])}</code>")
            continue
        t = html.escape(part, quote=False)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                   lambda m: f'<a href="{html.escape(_link(m.group(2)))}">{m.group(1)}</a>', t)
        t = re.sub(r"(?<![\w/\"=>])(https://[^\s<)]+[^\s<).,;:])",
                   lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', t)
        t = re.sub(r"(?<![\w.@/>])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,})(?![\w.])",
                   r'<a href="mailto:\1">\1</a>', t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])", r"<em>\1</em>", t)
        out.append(t)
    return "".join(out)


def markdown(text: str, *, drop_title: bool = True) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    i = 1 if drop_title and lines and lines[0].startswith("# ") else 0
    out: list[str] = []
    para: list[str] = []

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush()
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(block))}</code></pre>")
            i += 1
            continue
        m = re.match(r"^(#{1,4}) (.*)$", line)
        if m:
            flush()
            level = min(len(m.group(1)), 4)
            out.append(f'<h{level} id="{slug(m.group(2))}">{inline(m.group(2))}</h{level}>')
            i += 1
            continue
        if line.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], rows[2:]
            ths = "".join(f'<th scope="col">{inline(c)}</th>' for c in head)
            trs = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
            out.append(f'<div class="table-wrap"><table><thead><tr>{ths}</tr></thead>'
                       f"<tbody>{trs}</tbody></table></div>")
            continue
        if line.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip(">").strip())
                i += 1
            out.append(f"<blockquote><p>{inline(' '.join(quote))}</p></blockquote>")
            continue
        m = re.match(r"^(\s*)([-*]|\d+\.) (.*)$", line)
        if m:
            flush()
            ordered = m.group(2)[0].isdigit()
            items: list[str] = []
            while i < len(lines):
                m = re.match(r"^(\s*)([-*]|\d+\.) (.*)$", lines[i])
                if m:
                    items.append(m.group(3))
                elif lines[i].startswith("  ") and lines[i].strip() and items:
                    items[-1] += " " + lines[i].strip()
                else:
                    break
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(it)}</li>" for it in items) + f"</{tag}>")
            continue
        if not line.strip():
            flush()
        else:
            para.append(line.strip())
        i += 1
    flush()
    return "\n".join(out)


# ------------------------------------------------------------------- layout ---

def expand(text: str) -> str:
    """{{key}} placeholders from site.toml (site, links, donate)."""
    values = {**S, **L, **{f"donate_{k}": v for k, v in D.items()},
              "fingerprint": FPR_SPACED, "fingerprint_raw": FPR}
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", html.escape(str(value)))
    return text


def picture(name: str, ext: str, width: str, height: str, cls: str, alt: str) -> str:
    """A screenshot in the site's light and dark mode: the dark image when the
    system is dark, switched by site.js when the visitor overrides the theme."""
    light, dark = f"/assets/shots/{name}-light.{ext}", f"/assets/shots/{name}-dark.{ext}"
    lazy = "" if "hero" in cls.split() else ' loading="lazy"'
    img = (f'<picture><source data-scheme="dark" srcset="{dark}" media="(prefers-color-scheme: dark)">'
           f'<img src="{light}" width="{width}" height="{height}"{lazy} alt="{html.escape(alt)}"></picture>')
    if "bare" in cls.split():
        return img
    return f'<figure class="shot {html.escape(cls.strip())}">{img}</figure>'


def content(name: str) -> str:
    text = expand((SITE / "content" / name).read_text(encoding="utf-8"))
    # [[pic NAME EXT WIDTH HEIGHT CLASSES|ALT]]
    return re.sub(r"\[\[pic (\S+) (\S+) (\d+) (\d+) ?([^|\]]*)\|([^\]]+)\]\]",
                  lambda m: picture(*m.groups()), text)


def page(path: str, title: str, body: str, description: str, *, wide: bool = False) -> None:
    nav = "".join(f'<a href="{href}"{CURRENT if path.startswith(href) else ""}>{label}</a>'
                  for href, label in NAV)
    full_title = f"{S['product']}: {S['tagline']}" if path == "/" else f"{title} | {S['product']}"
    # Kept in the page, hidden, until SignPath approves the project (site.toml).
    hidden = "" if SIGNED else " hidden"
    signed = f'<p class="attribution"{hidden}>{html.escape(ATTRIBUTION)}.</p>'
    url = S["url"] + ("/404" if path == "/404" else path)
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="{url}">
<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="#0b1520" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#f6f7f9" media="(prefers-color-scheme: light)">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{html.escape(S['product'])}">
<meta property="og:title" content="{html.escape(full_title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{S['url']}/assets/og-image.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{html.escape(S['product'])} showing a traceroute from Manila to Germany on a world map with its hop table">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/assets/favicon-32.png" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="preload" href="/assets/fonts/plex-sans-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/archivo-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/style.css">
<script src="/assets/site.js"></script>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <div class="bar">
    <a class="wordmark" href="/"><img src="/assets/favicon-32.png" alt="" width="24" height="24"><span>{html.escape(S['product'])}</span></a>
    <nav aria-label="Main">{nav}<a class="gh" href="{L['repository']}">GitHub</a><button id="theme-toggle" class="theme-toggle" type="button" aria-pressed="false" hidden>Dark mode</button></nav>
  </div>
</header>
<main id="main"{' class="wide"' if wide else ''}>
{body}
</main>
<footer class="site-footer">
  <div class="bar">
    <p class="built">Built by <a href="{L['builder']}">{html.escape(L['builder_name'])}</a>.
    {html.escape(S['product'])} is free and open source under the
    <a href="{L['repository']}/blob/main/LICENSE">GNU AGPL-3.0</a>.</p>
    <p class="links"><a href="{L['repository']}">Source on GitHub</a>
    <a href="/privacy/">Privacy</a> <a href="/code-signing/">Code signing policy</a>
    <a href="/release-key.asc">Release key</a> <a href="/.well-known/security.txt">security.txt</a>
    <a href="mailto:{S['contact']}">{S['contact']}</a></p>
    <p class="release">Latest release: <a href="{L['releases']}/tag/{LATEST}">{LATEST}</a></p>
    {signed}
    <p class="quiet">This site sets no cookies and runs no analytics.</p>
  </div>
</footer>
</body>
</html>
"""
    target = OUT / "404.html" if path == "/404" else OUT / path.strip("/") / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(doc, encoding="utf-8")


def prose(title: str, inner: str, lead: str = "") -> str:
    lead_html = f'<p class="lead">{lead}</p>' if lead else ""
    return f'<article class="prose"><h1>{html.escape(title)}</h1>{lead_html}{inner}</article>'


DOC_PAGES = [("/docs/guide/", "guide.md", "User guide"), ("/docs/cli/", "cli.md", "Command line"),
             ("/docs/faq/", "faq.md", "Questions"),
             ("/docs/troubleshooting/", "troubleshooting.md", "Troubleshooting"),
             ("/docs/limitations/", "limitations.md", "Known limitations")]


def doc_nav(current: str) -> str:
    items = "".join(f'<li><a href="{p}"{CURRENT if p == current else ""}>{t}</a></li>'
                    for p, _f, t in DOC_PAGES)
    return f'<p class="eyebrow">Docs</p><ul>{items}</ul>'


def doc_page(path: str, source: pathlib.Path, title: str, description: str, lead: str = "",
             aside: str = "") -> None:
    body = prose(title, markdown(source.read_text(encoding="utf-8")), lead)
    if aside:
        body = f'<div class="doc-layout"><nav class="doc-nav" aria-label="Documentation">{aside}</nav>{body}</div>'
    page(path, title, body, description)


# ------------------------------------------------------------------ releases ---

def version_for(tag: str) -> str:
    """'v0.1.0-beta.4' -> '0.1.0b4': the spelling the release file names use."""
    m = re.match(r"^v?(\d+\.\d+\.\d+)(?:-(alpha|beta|rc)\.(\d+))?$", tag)
    if not m:
        return tag.lstrip("v")
    base, kind, n = m.groups()
    return base + ({"alpha": "a", "beta": "b", "rc": "rc"}[kind] + n if kind else "")


def tag_for(version: str) -> str:
    m = re.match(r"^(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?$", version)
    if not m:
        return "v" + version
    base, kind, n = m.groups()
    names = {"a": "alpha", "b": "beta", "rc": "rc"}
    return "v" + base + (f"-{names[kind]}.{n}" if kind else "")


class Release:
    def __init__(self, tag: str, release_json: str | None, sums: str | None):
        self.tag = tag
        self.version = version_for(tag)
        self.base = f"{L['releases']}/download/{tag}"
        self.sizes: dict[str, int] = {}
        self.date = ""
        if release_json:
            data = json.loads(pathlib.Path(release_json).read_text(encoding="utf-8"))
            self.sizes = {a["name"]: int(a["size"]) for a in data.get("assets", [])}
            self.date = (data.get("publishedAt") or "")[:10]
        self.sums: dict[str, str] = {}
        if sums:
            for line in pathlib.Path(sums).read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) == 2:
                    self.sums[parts[1].lstrip("*")] = parts[0]

    def files(self):
        for key, label, pattern, note in PLATFORMS:
            name = pattern.format(v=self.version)
            yield key, label, name, note, self.sizes.get(name), self.sums.get(name)


def size_text(n: int | None) -> str:
    return f"{n / 1_000_000:.0f} MB" if n else ""


PRIMARY = {"windows": ("windows", "Windows"), "macos": ("macos", "macOS"), "linux": ("linux", "Linux")}


def download_buttons(rel: Release) -> str:
    """One button for the visitor's platform, the others one line below.
    site.js marks the platform on <html>; the stylesheet shows the matching
    button. Without JavaScript (or an unknown platform) the button leads to the
    download page and every platform is listed on the line below."""
    files = {key: (label, name, size) for key, label, name, _n, size, _s in rel.files()}
    buttons = []
    for os_key, (file_key, short) in PRIMARY.items():
        _label, name, size = files[file_key]
        extra = f'<span class="size">{size_text(size)}</span>' if size else ""
        buttons.append(f'<a class="dl primary" data-os="{os_key}" href="{rel.base}/{name}">'
                       f"Download for {short}{extra}</a>")
    buttons.append('<a class="dl primary generic" href="/download/">Download</a>')
    others = " ".join(f'<a href="{rel.base}/{name}">{label}</a>'
                      for key, (label, name, _size) in files.items())
    return (f'<div class="downloads">{"".join(buttons)}</div>'
            f'<p class="dl-more">Also: {others}. {html.escape(rel.tag)}, '
            f'<a href="/download/">checksums and install steps</a>.</p>')


# --------------------------------------------------------------------- pages ---

def build_home(rel: Release) -> None:
    body = content("home.html").replace("{{downloads}}", download_buttons(rel)) \
                               .replace("{{tag}}", html.escape(rel.tag))
    page("/", S["product"], body, S["description"], wide=True)


def build_download(rel: Release) -> None:
    rows = []
    for key, label, name, note, size, sha in rel.files():
        rows.append(f'<tr><th scope="row">{label}<span class="note">{note}</span></th>'
                    f'<td><a href="{rel.base}/{name}">{name}</a>'
                    + (f'<code class="sha">{sha}</code>' if sha else "")
                    + f'</td><td class="num">{size_text(size)}</td></tr>')
    windows_note = (f"<p>The Windows build is code-signed. {html.escape(ATTRIBUTION)}.</p>"
                    if SIGNED else content("download-unsigned.html"))
    published = f", published {rel.date}" if rel.date else ""
    zip_name = next(rel.files())[2]
    body = f"""<article class="prose wide-prose">
<h1>Download {html.escape(S['product'])}</h1>
<p class="lead">Version <strong>{html.escape(rel.tag)}</strong>{published}, from
<a href="{L['releases']}/tag/{rel.tag}">GitHub Releases</a>. Free, no account.</p>
{download_buttons(rel)}
<div class="table-wrap"><table class="files">
<thead><tr><th scope="col">Platform</th><th scope="col">File and SHA-256</th><th scope="col" class="num">Size</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p>Release notes and every earlier version: <a href="{L['releases']}">github.com/osintph/routemap/releases</a>.
What changed: <a href="/changelog/">changelog</a>.</p>
<h2 id="first-start">First start</h2>
{windows_note}
{content("download-firststart.html")}
<h2 id="verify">Verify a download</h2>
<p>Every release has <a href="{rel.base}/SHA256SUMS"><code>SHA256SUMS</code></a> and its detached
GPG signature <a href="{rel.base}/SHA256SUMS.asc"><code>SHA256SUMS.asc</code></a>, made with the
release key <a href="/release-key.asc">release-key.asc</a>:</p>
<p class="fingerprint"><code>{FPR_SPACED}</code></p>
<pre><code>gpg --import release-key.asc
gpg --fingerprint {FPR}      # must show the fingerprint above
gpg --verify SHA256SUMS.asc SHA256SUMS
sha256sum -c SHA256SUMS --ignore-missing        # Linux
shasum -a 256 -c SHA256SUMS --ignore-missing    # macOS</code></pre>
<p>On Windows, compare <code>Get-FileHash .\\{html.escape(zip_name)}</code> in PowerShell with
the line for the zip in <code>SHA256SUMS</code>.</p>
</article>"""
    page("/download/", "Download", body,
         f"Download {S['product']} {rel.tag} for Windows, macOS and Linux from GitHub Releases, "
         "with SHA-256 checksums signed by the release key.")


def qr_svg(text: str, label: str) -> str:
    import segno
    svg = segno.make(text, error="m").svg_inline(scale=4, border=2, dark="#0b1520", light="#ffffff",
                                                 omitsize=True)
    return svg.replace("<svg ", f'<svg role="img" aria-label="QR code of the {html.escape(label)} address" ', 1)


def donation_block() -> str:
    links = "".join(f'<li><a class="pay" href="{url}"><strong>{html.escape(name)}</strong>'
                    f'<span>{html.escape(url.split("//", 1)[1])}</span></a></li>'
                    for name, url in (("Ko-fi", D["kofi"]), ("PayPal", D["paypal"])))
    coins = ""
    for name, key in (("Bitcoin", "bitcoin"), ("Monero", "monero")):
        address = D[key]
        kind = " (bech32)" if key == "bitcoin" else ""
        coins += (f'<figure class="coin"><div class="qr">{qr_svg(address, name)}</div>'
                  f'<figcaption><strong>{name}{kind}</strong><code class="address">{address}</code>'
                  f'</figcaption></figure>')
    asc = (SITE / "donate" / "addresses.txt.asc").exists()
    signed = ('<a href="/donate/addresses.txt.asc">addresses.txt.asc</a>, its signature by the '
              'release key' if asc else "its signature by the release key, which is being added")
    return f"""<p class="lead">Donations pay for {html.escape(D['pays_for'])}.</p>
<ul class="pay-list">{links}</ul>
<div class="coins">{coins}</div>
<p class="small">The addresses as text: <a href="/donate/addresses.txt">addresses.txt</a>, and {signed}
(<a href="/release-key.asc">key</a> <code>{FPR_SPACED}</code>). Compare the address in your
wallet with this page and the signed file before you send.</p>"""


def build_support() -> None:
    page("/donate/", "Donate", prose(f"Support {S['product']}", donation_block()),
         f"Donate to {S['product']}: Ko-fi, PayPal, Bitcoin or Monero. Donations pay for code signing, "
         "hosting, the RIPE Atlas probe and maintenance time.")
    body = prose("Support", content("support.html").replace("{{donations}}", donation_block()))
    page("/support/", "Support", body,
         f"Get help with {S['product']}, report a bug, or support the project with a donation.")


def build_docs() -> None:
    blurbs = ["Install, first trace, reading the result, exports, paste mode, settings, RIPE Atlas.",
              "Every command, option and exit code.",
              "Short answers to the usual questions.",
              "Defender, Gatekeeper, no trace tool, the origin behind a VPN.",
              "What Route Map does not do, or does not do yet."]
    index = "".join(f'<li><a href="{p}">{t}</a><span>{b}</span></li>'
                    for (p, _f, t), b in zip(DOC_PAGES, blurbs))
    page("/docs/", "Docs", prose("Documentation", f'<ul class="doc-index">{index}</ul>'),
         f"{S['product']} documentation: user guide, command line, questions, troubleshooting and limitations.")
    descriptions = {
        "guide.md": f"How to install and use {S['product']}: first trace, source labels, exports, paste mode, settings and RIPE Atlas.",
        "cli.md": f"{S['product']} command-line reference: commands, options, exit codes and examples.",
        "faq.md": f"Questions about {S['product']}: warnings, cost, sources, privacy, pasted traces.",
        "troubleshooting.md": f"Fixing common {S['product']} problems: Defender, Gatekeeper, missing traceroute, VPN origin.",
        "limitations.md": f"Known limitations of {S['product']}: unsigned builds, IP database hints, what traceroute cannot see.",
    }
    for path, name, title in DOC_PAGES:
        doc_page(path, ROOT / "docs" / name, title, descriptions[name], aside=doc_nav(path))


def build_static_pages(rel: Release) -> None:
    page("/screenshots/", "Screenshots", content("screenshots.html"),
         f"Screenshots of {S['product']} {rel.tag}: light and dark, macOS and Windows, PNG and PDF exports.",
         wide=True)
    page("/about/", "About", prose(f"About {S['product']}", content("about.html")),
         f"Who builds {S['product']} and why: OSINTPH, the FalconEye Route Map tab, and how to get in touch.")
    doc_page("/privacy/", ROOT / "PRIVACY.md", "Privacy",
             f"What {S['product']} sends, to whom and when; what stays on your machine; what this site logs.",
             lead=content("privacy-lead.html"))
    doc_page("/code-signing/", ROOT / "CODE_SIGNING_POLICY.md", "Code signing policy",
             f"How {S['product']} Windows releases are signed through SignPath Foundation, and by whom.")
    changelog = markdown((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    changelog = re.sub(r"<p>All notable changes.*?</p>", "", changelog, flags=re.S)
    changelog = re.sub(r'<h2 id="unreleased">Unreleased</h2>\s*', "", changelog)
    page("/changelog/", "Changelog", prose("Changelog", changelog,
         f'Every release, newest first. Downloads: <a href="{L["releases"]}">GitHub Releases</a>.'),
         f"What changed in each {S['product']} release.")
    page("/404", "Not found", prose("Not found", content("404.html")), "Page not found.")


def build_files() -> None:
    shutil.copy2(SITE / "assets" / "release-key.asc", OUT / "release-key.asc")
    shutil.copy2(SITE / "assets" / "favicon.ico", OUT / "favicon.ico")
    donate = OUT / "donate"
    donate.mkdir(parents=True, exist_ok=True)
    for name in ("addresses.txt", "addresses.txt.asc"):
        if (SITE / "donate" / name).exists():
            shutil.copy2(SITE / "donate" / name, donate / name)
    expires = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=330)).strftime("%Y-%m-%dT00:00:00Z")
    well_known = OUT / ".well-known"
    well_known.mkdir(exist_ok=True)
    (well_known / "security.txt").write_text(
        f"Contact: mailto:{S['contact']}\n"
        f"Expires: {expires}\n"
        f"Encryption: {S['url']}/release-key.asc\n"
        f"Preferred-Languages: en\n"
        f"Canonical: {S['url']}/.well-known/security.txt\n", encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {S['url']}/sitemap.xml\n",
                                    encoding="utf-8")
    (OUT / "site.webmanifest").write_text(json.dumps({
        "name": S["product"], "short_name": S["product"], "start_url": "/",
        "icons": [{"src": "/assets/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/assets/icon-512.png", "sizes": "512x512", "type": "image/png"}],
        "background_color": "#0b1520", "theme_color": "#0b1520", "display": "browser"}, indent=1),
        encoding="utf-8")
    pages = []
    for p in sorted(OUT.rglob("index.html")):
        rel = p.parent.relative_to(OUT).as_posix()
        pages.append("/" if rel == "." else f"/{rel}/")
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{S['url']}{p}</loc></url>\n" for p in pages) + "</urlset>\n",
        encoding="utf-8")


def main(argv: list[str]) -> int:
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default=tag_for(__version__))
    parser.add_argument("--release-json")
    parser.add_argument("--sums")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    OUT = pathlib.Path(args.out)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copytree(SITE / "assets", OUT / "assets")
    global LATEST
    rel = Release(args.tag, args.release_json, args.sums)
    LATEST = rel.tag
    build_home(rel)
    build_download(rel)
    build_support()
    build_docs()
    build_static_pages(rel)
    build_files()
    count = sum(1 for _ in OUT.rglob("*.html"))
    print(f"{count} pages in {OUT} for {rel.tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
