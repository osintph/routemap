"""
Build the project site (getroutemap.app) into site/build/. Standard library only.

    python site/build.py [--sums release/SHA256SUMS] [--tag v0.1.0-beta.4]

- Branding and links come from site/site.toml, so a domain or name change is
  one edit there.
- Page text comes from the repository's own documents wherever one exists
  (docs/guide.md, docs/cli.md, PRIVACY.md, CODE_SIGNING_POLICY.md), so the site
  and the repository cannot drift apart. The rest is in site/content/.
- No JavaScript, no external assets, no cookies, no analytics. Light and dark
  follow the reader's system setting.
- The download page links the GitHub Release for --tag (default: the version in
  routemap/__about__.py) and lists the SHA-256 of each file when --sums is given.
"""
from __future__ import annotations

import argparse
import html
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
S, L = CONFIG["site"], CONFIG["links"]

NAV = [("/", "Home"), ("/download/", "Download"), ("/screenshots/", "Screenshots"),
       ("/docs/", "Docs"), ("/faq/", "FAQ"), ("/support/", "Support")]

# Repository documents that have a page here; anything else links to GitHub.
LOCAL_DOCS = {"PRIVACY.md": "/privacy/", "CODE_SIGNING_POLICY.md": "/code-signing/",
              "cli.md": "/docs/cli/", "guide.md": "/docs/"}


# ------------------------------------------------------------------ markdown ---
# The subset the project's documents use: headings, paragraphs, lists, tables,
# fenced code, block quotes, and inline code, bold, italics and links.

def _link(url: str) -> str:
    base = url.split("#")[0]
    name = base.rsplit("/", 1)[-1]
    if name in LOCAL_DOCS:
        return LOCAL_DOCS[name]
    if base and not re.match(r"^[a-z]+:|^/|^#", base):
        return f"{L['repository']}/blob/main/{base.lstrip('./')}"
    return url


def inline(text: str) -> str:
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(f"<code>{html.escape(part[1:-1])}</code>")
            continue
        t = html.escape(part, quote=False)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                   lambda m: f'<a href="{html.escape(_link(m.group(2)))}">{m.group(1)}</a>', t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])", r"<em>\1</em>", t)
        out.append(t)
    return "".join(out)


def markdown(text: str, *, drop_title: bool = False) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    html_out: list[str] = []
    i = 0
    if drop_title and lines and lines[0].startswith("# "):
        i = 1
    para: list[str] = []

    def flush():
        if para:
            html_out.append(f"<p>{inline(' '.join(para))}</p>")
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
            html_out.append(f"<pre><code>{html.escape(chr(10).join(block))}</code></pre>")
            i += 1
            continue
        m = re.match(r"^(#{1,4}) (.*)$", line)
        if m:
            flush()
            level = len(m.group(1)) + (1 if drop_title else 0)
            level = min(level, 4)
            slug = re.sub(r"[^a-z0-9]+", "-", m.group(2).lower()).strip("-")
            html_out.append(f'<h{level} id="{slug}">{inline(m.group(2))}</h{level}>')
            i += 1
            continue
        if line.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[2:]]
            cells = "".join(f"<th>{inline(c)}</th>" for c in head)
            trs = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
            html_out.append(f'<div class="table"><table><thead><tr>{cells}</tr></thead>'
                            f"<tbody>{trs}</tbody></table></div>")
            continue
        if line.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip(">").strip())
                i += 1
            html_out.append(f"<blockquote><p>{inline(' '.join(quote))}</p></blockquote>")
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
            html_out.append(f"<{tag}>" + "".join(f"<li>{inline(it)}</li>" for it in items) + f"</{tag}>")
            continue
        if not line.strip():
            flush()
        else:
            para.append(line.strip())
        i += 1
    flush()
    return "\n".join(html_out)


# ------------------------------------------------------------------- layout ---

def page(path: str, title: str, body: str, *, description: str = "") -> None:
    current = ' aria-current="page"'
    links = "".join(f'<a href="{href}"{current if href == path else ""}>{label}</a>'
                    for href, label in NAV)
    sig = CONFIG["signing"]
    signed = f"<p>{html.escape(sig['signpath_attribution'])}.</p>" if sig["signpath_signed"] else ""
    full_title = S["product"] if path == "/" else f"{title} · {S['product']}"
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{html.escape(description or S['description'])}">
<link rel="canonical" href="{S['url']}{path}">
<link rel="icon" href="/assets/icon.png">
<link rel="stylesheet" href="/assets/style.css">
<meta name="color-scheme" content="light dark">
</head>
<body>
<header class="top">
  <a class="brand" href="/"><img src="/assets/icon.png" alt="" width="28" height="28">{html.escape(S['product'])}</a>
  <nav aria-label="Main">{links}</nav>
</header>
<main>
{body}
</main>
<footer>
  <p>Built by <a href="{L['builder']}">{html.escape(L['builder_name'])}</a>.
  {html.escape(S['product'])} is free software under the
  <a href="{L['repository']}/blob/main/LICENSE">GNU AGPL-3.0</a>.
  <a href="{L['repository']}">Source on GitHub</a> ·
  <a href="/privacy/">Privacy</a> · <a href="/code-signing/">Code signing policy</a></p>
  {signed}
  <p>This site sets no cookies and runs no analytics or scripts.</p>
</footer>
</body>
</html>
"""
    target = OUT / path.strip("/") / "index.html" if path != "/404" else OUT / "404.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(doc, encoding="utf-8")


def doc_page(path: str, source: pathlib.Path, title: str, intro: str = "") -> None:
    body = markdown(source.read_text(encoding="utf-8"), drop_title=True)
    page(path, title, f'<article class="prose"><h1>{html.escape(title)}</h1>{intro}{body}</article>')


def content(name: str) -> str:
    text = (SITE / "content" / name).read_text(encoding="utf-8")
    for key, value in {**S, **L}.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


# ----------------------------------------------------------------- download ---

def tag_for(version: str) -> str:
    m = re.match(r"^(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?$", version)
    if not m:
        return "v" + version
    base, kind, n = m.groups()
    names = {"a": "alpha", "b": "beta", "rc": "rc"}
    return "v" + base + (f"-{names[kind]}.{n}" if kind else "")


def version_for(tag: str) -> str:
    """'v0.1.0-beta.4' -> '0.1.0b4': the spelling the release file names use."""
    m = re.match(r"^v?(\d+\.\d+\.\d+)(?:-(alpha|beta|rc)\.(\d+))?$", tag)
    if not m:
        return tag.lstrip("v")
    base, kind, n = m.groups()
    return base + ({"alpha": "a", "beta": "b", "rc": "rc"}[kind] + n if kind else "")


def download_body(tag: str, sums: dict[str, str]) -> str:
    version = version_for(tag)
    base = f"{L['releases']}/download/{tag}"
    rows = [
        ("Windows 10/11 (x86_64)", f"routemap-{version}-windows-x86_64.zip",
         "Extract, then run <code>routemap.exe</code> in the <code>Route Map</code> folder."),
        ("macOS 12+ (Apple silicon)", f"routemap-{version}-macos-arm64.dmg", "Drag Route Map to Applications."),
        ("macOS 12+ (Intel)", f"routemap-{version}-macos-x86_64.dmg", "Drag Route Map to Applications."),
        ("Linux x86_64, AppImage", f"routemap-{version}-linux-x86_64.AppImage", "<code>chmod +x</code>, then run."),
        ("Linux x86_64, tar.gz", f"routemap-{version}-linux-x86_64.tar.gz", "Unpack, run <code>./routemap</code>."),
    ]
    trs = []
    for label, name, how in rows:
        digest = sums.get(name)
        trs.append(f'<tr><td>{label}</td><td><a href="{base}/{name}">{name}</a>'
                   + (f'<br><code class="sha">{digest}</code>' if digest else "")
                   + f"</td><td>{how}</td></tr>")
    fpr = CONFIG["release"]["gpg_fingerprint"]
    fpr_spaced = " ".join(fpr[i:i + 4] for i in range(0, len(fpr), 4))
    sig = CONFIG["signing"]
    windows_note = (f"<p>The Windows build is code-signed. {html.escape(sig['signpath_attribution'])}.</p>"
                    if sig["signpath_signed"] else content("download-unsigned.html"))
    return f"""<article class="prose">
<h1>Download {html.escape(S['product'])}</h1>
<p class="lead">Version <strong>{html.escape(tag)}</strong>, from
<a href="{L['releases']}/tag/{tag}">GitHub Releases</a>. Free, no account, no sign-up.</p>
<div class="table"><table>
<thead><tr><th>Platform</th><th>File (SHA-256)</th><th>Install</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
<p>All releases, with release notes: <a href="{L['releases']}">github.com/osintph/routemap/releases</a>.</p>
<h2 id="first-start">First start</h2>
{windows_note}
{content("download-firststart.html")}
<h2 id="verify">Verify your download</h2>
<p>Each release has <a href="{base}/SHA256SUMS"><code>SHA256SUMS</code></a> and its GPG signature
<a href="{base}/SHA256SUMS.asc"><code>SHA256SUMS.asc</code></a>, made with the release key</p>
<p><code class="fpr">{fpr_spaced}</code></p>
<pre><code>gpg --verify SHA256SUMS.asc SHA256SUMS
sha256sum -c SHA256SUMS --ignore-missing        # Linux
shasum -a 256 -c SHA256SUMS --ignore-missing    # macOS
Get-FileHash .\\routemap-{version}-windows-x86_64.zip   # Windows PowerShell</code></pre>
<p>Import the public key first: download <a href="/assets/release-key.asc">release-key.asc</a>
(also <a href="{L['repository']}/blob/main/RELEASE-KEY.asc">RELEASE-KEY.asc</a> in the repository),
run <code>gpg --import release-key.asc</code>, and check that
<code>gpg --fingerprint {fpr}</code> shows the fingerprint above.</p>
</article>"""


def read_sums(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    sums = {}
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1].lstrip("*")] = parts[0]
    return sums


# --------------------------------------------------------------------- build ---

def main(argv: list[str]) -> int:
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--sums")
    parser.add_argument("--tag", default=tag_for(__version__))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    OUT = pathlib.Path(args.out)

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copytree(SITE / "assets", OUT / "assets")

    page("/", S["product"], content("home.html"))
    page("/download/", "Download", download_body(args.tag, read_sums(args.sums)))
    page("/screenshots/", "Screenshots", content("screenshots.html"))
    doc_page("/docs/", ROOT / "docs" / "guide.md", "User guide",
             '<p class="lead">Also: <a href="/docs/cli/">command-line reference</a>.</p>')
    doc_page("/docs/cli/", ROOT / "docs" / "cli.md", "Command-line reference")
    doc_page("/privacy/", ROOT / "PRIVACY.md", "Privacy",
             '<p class="lead">The same text as <a href="'
             f'{L["repository"]}/blob/main/PRIVACY.md">PRIVACY.md</a> in the repository and '
             "Help &gt; Privacy in the app. This website itself sets no cookies and runs no "
             "analytics; the server keeps a standard access log.</p>")
    doc_page("/code-signing/", ROOT / "CODE_SIGNING_POLICY.md", "Code signing policy")
    page("/faq/", "FAQ", content("faq.html"))
    page("/support/", "Support", content("support.html").replace(
        "{{contact}}", (f'<p>If you would rather not use GitHub, email '
                        f'<a href="mailto:{L["contact_email"]}">{L["contact_email"]}</a>.</p>'
                        if L["contact_email"] else "")))
    page("/404", "Not found", '<article class="prose"><h1>Not found</h1>'
         '<p>That page does not exist. <a href="/">Back to the start</a>.</p></article>')
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {S['url']}/sitemap.xml\n",
                                    encoding="utf-8")
    urls = ["/", "/download/", "/screenshots/", "/docs/", "/docs/cli/", "/privacy/",
            "/code-signing/", "/faq/", "/support/"]
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{S['url']}{u}</loc></url>\n" for u in urls) + "</urlset>\n",
        encoding="utf-8")
    pages = sorted(p.relative_to(OUT) for p in OUT.rglob("*.html"))
    print(f"{len(pages)} pages in {OUT} for {args.tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
