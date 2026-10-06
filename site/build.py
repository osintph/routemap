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
SIGNED = CONFIG["signing"]["windows_signed"]
FPR = CONFIG["release"]["gpg_fingerprint"]
GA_ID = CONFIG.get("analytics", {}).get("ga_measurement_id", "")
if GA_ID and not re.fullmatch(r"G-[A-Z0-9]{4,20}", GA_ID):
    raise SystemExit(f"site.toml: ga_measurement_id {GA_ID!r} is not a G- measurement ID")
FPR_SPACED = " ".join(FPR[i:i + 4] for i in range(0, len(FPR), 4))
CURRENT = ' aria-current="page"'
LATEST = ""   # the release tag the site describes; set in main()
# Content hashes in the stylesheet and script URLs: a changed file gets a new
# URL, so no browser or Cloudflare cache can serve the old one with new pages.
ASSET_VERSION = {}

NAV = [("/download/", "Download"), ("/docs/", "Docs"), ("/screenshots/", "Screenshots"),
       ("/changelog/", "Changelog"), ("/support/", "Support"), ("/about/", "About")]

# Repository documents that have a page here; any other relative link goes to GitHub.
LOCAL_DOCS = {"PRIVACY.md": "/privacy/", "CODE_SIGNING_POLICY.md": "/code-signing/",
              "CHANGELOG.md": "/changelog/", "guide.md": "/docs/guide/", "cli.md": "/docs/cli/",
              "faq.md": "/docs/faq/", "limitations.md": "/docs/limitations/",
              "troubleshooting.md": "/docs/troubleshooting/", "testing.md": "/docs/testing/",
              "reading-a-traceroute.md": "/docs/reading-a-traceroute/",
              "RELEASE-KEY.asc": "/release-key.asc"}

PLATFORMS = [
    # key, group, label, file pattern, note. Per platform the installer comes
    # first. {v} is the version; a * in a pattern is filled in from the release's files.
    ("windows", "windows", "Installer", "routemap-{v}-windows-x86_64-setup.exe",
     "Windows 10/11, x86_64; Start menu, uninstaller, upgrades in place"),
    ("windows-zip", "windows", "Zip", "routemap-{v}-windows-x86_64.zip", "no install: extract and run"),
    ("macos", "macos", "Apple silicon", "routemap-{v}-macos-arm64.dmg", "macOS 12+, dmg"),
    ("macos-intel", "macos", "Intel", "routemap-{v}-macos-x86_64.dmg", "macOS 12+, dmg"),
    ("linux-deb", "linux", "Debian, Ubuntu (.deb)", "routemap-{v}-linux-x86_64.deb", "x86_64, apt; menu entry"),
    ("linux-rpm", "linux", "Fedora, RHEL, openSUSE (.rpm)", "routemap-{v}-linux-x86_64.rpm",
     "x86_64, dnf or zypper; menu entry"),
    ("linux", "linux", "AppImage", "routemap-{v}-linux-x86_64.AppImage", "x86_64, any distribution, no install"),
    ("linux-tar", "linux", "tar.gz", "routemap-{v}-linux-x86_64.tar.gz", "x86_64, no install"),
]
GROUPS = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}


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
        # removeprefix, not lstrip: lstrip("./") also ate the dot of ".github/".
        return f"{L['repository']}/blob/main/{base.removeprefix('./')}" + (f"#{anchor}" if anchor else "")
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


def img_url(path: str) -> str:
    """/assets/img/NAME with a content hash, so a retaken screenshot is a new URL
    and never a stale copy from Cloudflare's cache (0.2.0's first deploy served
    beta.5's images for the same names)."""
    import hashlib
    file = SITE / path.lstrip("/")
    if not file.exists():
        return path
    return f"{path}?v={hashlib.sha256(file.read_bytes()).hexdigest()[:10]}"


# Screenshots are served as AVIF and WebP with the original format as the
# fallback, each at these widths up to the image's own, so a phone gets a file
# sized for it. Google Images supports all three formats in <picture> with an
# <img src> fallback (developers.google.com/search/docs/appearance/google-images).
VARIANT_WIDTHS = (480, 800, 1200, 1600, 2400)
VARIANT_FORMATS = (("avif", "image/avif", {"quality": 62, "speed": 6}),
                   ("webp", "image/webp", {"quality": 82, "method": 5}))
_VARIANTS: dict[str, dict] = {}


def variants(path: str) -> dict:
    """{"avif"|"webp"|"orig": "url 480w, url 800w, ..."} for /assets/img/NAME,
    written into the build once. File names carry the source's content hash, so
    a retaken screenshot is a new URL (see img_url)."""
    if path in _VARIANTS:
        return _VARIANTS[path]
    import hashlib
    from PIL import Image
    src = SITE / path.lstrip("/")
    digest = hashlib.sha256(src.read_bytes()).hexdigest()[:10]
    out_dir = OUT / "assets" / "img" / "v"
    out_dir.mkdir(parents=True, exist_ok=True)
    image = Image.open(src)
    image.load()
    widths = [w for w in VARIANT_WIDTHS if w < image.width] + [image.width]
    sets: dict[str, list[str]] = {"avif": [], "webp": [], "orig": []}
    orig_ext = src.suffix.lstrip(".").lower()
    for w in widths:
        size = (w, max(1, round(image.height * w / image.width)))
        frame = image if w == image.width else image.resize(size, Image.LANCZOS)
        for ext, _mime, opts in VARIANT_FORMATS + ((orig_ext, "", {}),):
            name = f"{src.stem}-{digest}-{w}.{ext}"
            target = out_dir / name
            if not target.exists():
                rgb = frame.convert("RGB") if ext in ("jpg", "jpeg") and frame.mode != "RGB" else frame
                fmt = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "avif": "AVIF", "webp": "WEBP"}[ext]
                extra = {"quality": 86, "optimize": True, "progressive": True} if fmt == "JPEG" else (
                    {"optimize": True} if fmt == "PNG" else opts)
                rgb.save(target, fmt, **extra)
            key = "orig" if ext == orig_ext else ext
            sets[key].append(f"/assets/img/v/{name} {w}w")
    _VARIANTS[path] = {k: ", ".join(v) for k, v in sets.items()}
    return _VARIANTS[path]


def picture(name: str, ext: str, width: str, height: str, cls: str, alt: str) -> str:
    """A screenshot in the site's light and dark mode: the dark image when the
    system is dark, switched by site.js when the visitor overrides the theme
    (it sets the media of every source marked data-scheme). Each scheme comes as
    AVIF, then WebP, then the original format, in several widths. A screenshot
    with no dark version is shown as it is in both schemes."""
    classes = cls.split()
    light_path, dark_path = f"/assets/img/{name}-light.{ext}", f"/assets/img/{name}-dark.{ext}"
    if not (SITE / light_path.lstrip("/")).exists():
        light_path, dark_path = f"/assets/img/{name}.{ext}", ""
    has_dark = bool(dark_path) and (SITE / dark_path.lstrip("/")).exists()
    # The crops are wider than a phone on purpose (they scroll); the rest fill the column.
    sizes = ("(max-width: 700px) 760px, 1160px" if "crop" in classes
             else "(max-width: 1208px) calc(100vw - 48px), 1160px")
    lazy = "" if "hero" in classes else ' loading="lazy"'
    fetch = ' fetchpriority="high"' if "hero" in classes else ""
    parts = []
    if has_dark:
        dv = variants(dark_path)
        for key, mime in (("avif", "image/avif"), ("webp", "image/webp"), ("orig", "")):
            type_attr = f' type="{mime}"' if mime else ""
            parts.append(f'<source data-scheme="dark" media="(prefers-color-scheme: dark)"{type_attr} '
                         f'srcset="{dv[key]}" sizes="{sizes}">')
    lv = variants(light_path)
    for key, mime in (("avif", "image/avif"), ("webp", "image/webp")):
        parts.append(f'<source type="{mime}" srcset="{lv[key]}" sizes="{sizes}">')
    img = (f'<picture>{"".join(parts)}<img src="{img_url(light_path)}" srcset="{lv["orig"]}" sizes="{sizes}" '
           f'width="{width}" height="{height}"{lazy}{fetch} decoding="async" alt="{html.escape(alt)}"></picture>')
    if "bare" in cls.split():
        return img
    return f'<figure class="shot {html.escape(cls.strip())}">{img}</figure>'


def content(name: str) -> str:
    text = expand((SITE / "content" / name).read_text(encoding="utf-8"))
    # <!--ga-->...<!--/ga--> only with Google Analytics configured, <!--no-ga-->...<!--/no-ga--> only without.
    keep, drop = ("ga", "no-ga") if GA_ID else ("no-ga", "ga")
    text = re.sub(rf"<!--{drop}-->.*?<!--/{drop}-->\n?", "", text, flags=re.S)
    text = re.sub(rf"<!--/?{keep}-->\n?", "", text)
    text = re.sub(r'src="(/assets/img/[^"?]+)"', lambda m: f'src="{img_url(m.group(1))}"', text)
    # [[pic NAME EXT WIDTH HEIGHT CLASSES|ALT]]
    return re.sub(r"\[\[pic (\S+) (\S+) (\d+) (\d+) ?([^|\]]*)\|([^\]]+)\]\]",
                  lambda m: picture(*m.groups()), text)


OG_DEFAULT = ("/assets/og/home.jpg",
              "{product}: see where your packets actually went, beside the app showing a trace from Manila to Frankfurt")


# Shared previews (Open Graph, 1200 x 630) for the pages people link to most;
# made from the site's own type and colours by site/og/make_og.py.
OG_DOWNLOAD = ("/assets/og/download.jpg", "Download {product}: free and open source for Windows, macOS and Linux")
OG_DOCS = ("/assets/og/docs.jpg", "{product} documentation")


def jsonld(*objects: dict) -> str:
    """<script type="application/ld+json"> blocks. Only facts the page itself
    shows go in (developers.google.com/search/docs/appearance/structured-data/sd-policies)."""
    return "".join('<script type="application/ld+json">'
                   + json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
                   + "</script>\n" for o in objects)


def organization() -> dict:
    """OSINTPH, named in every page's footer ("Built by OSINTPH")."""
    return {"@type": "Organization", "@id": f"{S['url']}/#osintph", "name": L["builder_name"], "url": L["builder"]}


def software(rel: "Release", operating_systems: str) -> dict:
    """Route Map as a SoftwareApplication, with what the page states: free, the
    platforms, the current version, the licence and where to download it.
    Google shows a software rich result only with a rating or review, which the
    project does not have, so this describes the app without asking for one
    (developers.google.com/search/docs/appearance/structured-data/software-app)."""
    return {"@context": "https://schema.org", "@type": "SoftwareApplication", "@id": f"{S['url']}/#app",
            "name": S["product"], "url": f"{S['url']}/", "description": S["description"],
            "applicationCategory": "UtilitiesApplication", "operatingSystem": operating_systems,
            "softwareVersion": rel.tag.lstrip("v"), "downloadUrl": f"{S['url']}/download/",
            "license": f"{L['repository']}/blob/main/LICENSE", "isAccessibleForFree": True,
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
            "publisher": organization()}


# The title and meta description each page shows in search results, written for
# what people search for (approved 5 Oct 2026): one page per intent, the product
# named once, the important words first because results shorten both to fit
# the screen (developers.google.com/search/docs/appearance/title-link and
# /snippet). None keeps the page's own description.
SEARCH = {
    "/": ("{p}: free, open source visual traceroute on a world map",
          "See a traceroute on a world map. {p} places each router by its hostname and checks it against the "
          "round-trip time. Free and open source for Windows, macOS and Linux."),
    "/download/": ("Download {p} for Windows, macOS and Linux",
                   "Free download of {p}, a visual traceroute: Windows installer, macOS DMG for Apple silicon and "
                   "Intel, Linux .deb, .rpm and AppImage, with signed checksums."),
    "/docs/": ("{p} documentation",
               "How to install {p}, run a first trace, read the map and the hop table, use the command line, and "
               "fix common problems."),
    "/docs/guide/": ("{p} user guide: install, trace and read the map",
                     "Install {p}, run a first trace and read the result: what each source label means, the route "
                     "summary, exports, pasting a trace, settings and RIPE Atlas."),
    "/docs/reading-a-traceroute/": ("How to read a traceroute: hops, round-trip times and stars",
                                    "What each line of a traceroute means, why round-trip times jump or drop, what "
                                    "the stars mean, and how to tell a slow hop from a slow path."),
    "/docs/cli/": ("{p} command line: trace, parse and export from a terminal",
                   "Run a trace, map an existing traceroute or tracert output, and export JSON, PNG or PDF from a "
                   "terminal. Every command, option and exit code."),
    "/docs/faq/": ("{p} questions and answers",
                   "Short answers about {p}: why Windows and macOS warn on first start, what it costs, where "
                   "locations come from, what it sends, and pasted traces."),
    "/docs/troubleshooting/": ("{p} troubleshooting: Defender, Gatekeeper and traces",
                               "Fixes for common {p} problems: Defender or SmartScreen on Windows, Gatekeeper on "
                               "macOS, traces that do not start, and an origin that is wrong behind a VPN."),
    "/docs/limitations/": ("What {p} cannot do (yet)",
                           "The limits of {p} and of traceroute itself: unsigned builds, how good an IP database "
                           "location is, and what a trace cannot show."),
    "/docs/testing/": ("Testing a {p} beta",
                       "Which file to install for a {p} beta, what to try, how to check the exact build, and how "
                       "to report what you found without exposing your own network."),
    "/screenshots/": ("{p} screenshots: map, globe, comparison and exports",
                      "{p} on macOS and Windows in light and dark: the map, the globe, comparing two runs, the hop "
                      "table, and the PNG and PDF exports."),
    "/compare/": ("{p} and commercial visual traceroute tools",
                  "How {p} differs from paid visual traceroute tools: price, platforms, source code, and how each "
                  "hop gets its location. Facts with sources."),
    "/about/": ("About {p} and OSINTPH",
                "Who builds {p} and why, its sister tool in FalconEye, and how to get in touch."),
    "/support/": ("{p} support: questions and bug reports",
                  "Get help with {p}, report a bug or a wrong placement, or support the project."),
    "/donate/": ("Donate to {p}", None),
    "/privacy/": ("{p} privacy: what the app sends and to whom", None),
    "/code-signing/": ("{p} code signing policy", None),
    "/changelog/": ("{p} changelog: what changed in each release",
                    "Every {p} release and what changed in it, newest first."),
}


def consent_head() -> str:
    """The measurement ID and the consent script, only when Analytics is configured.
    No Google URL is in any page: consent.js adds gtag.js after consent."""
    if not GA_ID:
        return ""
    return (f'<meta name="ga-measurement-id" content="{GA_ID}">\n'
            f'<script src="/assets/consent.js?v={ASSET_VERSION["consent.js"]}" defer></script>\n')


def consent_banner() -> str:
    """Accept and Reject as the same kind of button, side by side. Hidden until
    consent.js finds no stored choice; without JavaScript nothing loads and
    nothing is asked."""
    if not GA_ID:
        return ""
    return """<div id="consent" class="consent" role="region" aria-label="Cookie choice" hidden>
  <div class="bar">
    <p>May this site use <strong>Google Analytics</strong> cookies to count visits and downloads?
    Nothing is sent to Google unless you accept, and you can change your mind at any time under
    Cookie settings at the foot of every page. <a href="/privacy/#google-analytics">Details</a></p>
    <p class="consent-buttons"><button type="button" class="consent-button" data-consent="granted">Accept analytics cookies</button>
    <button type="button" class="consent-button" data-consent="denied">Reject analytics cookies</button></p>
  </div>
</div>
"""


def cookie_settings_link() -> str:
    return '\n    <a href="/privacy/#google-analytics" id="cookie-settings" data-cookie-settings>Cookie settings</a>' if GA_ID else ""


def analytics_note() -> str:
    if not GA_ID:
        return ('<p class="quiet">This website counts visits with Cloudflare Web Analytics, which sets no cookies;\n'
                '    the desktop app has no telemetry. <a href="/privacy/#this-website">Details</a>.</p>')
    return ('<p class="quiet">This website counts visits with Cloudflare Web Analytics, which sets no cookies, and,\n'
            '    only if you accept them, with Google Analytics cookies; the desktop app has no telemetry.\n'
            '    <a href="/privacy/#this-website">Details</a>.</p>')


def page(path: str, title: str, body: str, description: str, *, wide: bool = False,
         og: tuple[str, str] | None = None, structured: str = "") -> None:
    nav = "".join(f'<a href="{href}"{CURRENT if path.startswith(href) else ""}>{label}</a>'
                  for href, label in NAV)
    full_title = f"{S['product']}: {S['tagline']}" if path == "/" else f"{title} | {S['product']}"
    if path in SEARCH:
        search_title, search_description = SEARCH[path]
        full_title = search_title.format(p=S["product"])
        if search_description:
            description = search_description.format(p=S["product"])
    url = S["url"] + path
    og_path, og_alt = og or OG_DEFAULT
    og_alt = og_alt.format(product=S["product"])
    # The 404 page has no URL of its own to name as canonical or to share.
    identity = "" if path == "/404" else (f'<link rel="canonical" href="{url}">\n'
                                         f'<meta property="og:url" content="{url}">\n')
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{html.escape(description)}">
{identity}<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="#0b1520" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#f6f7f9" media="(prefers-color-scheme: light)">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{html.escape(S['product'])}">
<meta property="og:title" content="{html.escape(full_title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:image" content="{S['url']}{img_url(og_path)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{html.escape(og_alt)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image:alt" content="{html.escape(og_alt)}">
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/assets/favicon-32.png" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="preload" href="{img_url('/assets/fonts/schibsted-grotesk-var.woff2')}" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{img_url('/assets/fonts/newsreader-var.woff2')}" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/style.css?v={ASSET_VERSION['style.css']}">
<script src="/assets/site.js?v={ASSET_VERSION['site.js']}"></script>
{consent_head()}{structured}</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <div class="bar">
    <a class="wordmark" href="/"><img src="/assets/favicon-32.png" srcset="/assets/favicon-32.png 32w, /assets/favicon-64.png 64w" sizes="24px" alt="" width="24" height="24"><span>{html.escape(S['product'])}</span></a>
    <nav aria-label="Main">{nav}<a class="gh" href="{L['repository']}">GitHub</a></nav>
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
    <a href="/compare/">Compared with paid tools</a>
    <a href="/privacy/">Privacy</a> <a href="/code-signing/">Code signing policy</a>
    <a href="/release-key.asc">Release key</a> <a href="/.well-known/security.txt">security.txt</a>{cookie_settings_link()}
    <a href="mailto:{S['contact']}">{S['contact']}</a></p>
    <p class="release">Latest release: <a href="{L['releases']}/tag/{LATEST}">{LATEST}</a></p>
    {analytics_note()}
  </div>
</footer>
{consent_banner()}</body>
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
             ("/docs/limitations/", "limitations.md", "Known limitations"),
             ("/docs/testing/", "testing.md", "Testing a beta"),
             ("/docs/reading-a-traceroute/", "reading-a-traceroute.md", "How to read a traceroute")]


def doc_nav(current: str) -> str:
    items = "".join(f'<li><a href="{p}"{CURRENT if p == current else ""}>{t}</a></li>'
                    for p, _f, t in DOC_PAGES)
    return f'<p class="eyebrow">Docs</p><ul>{items}</ul>'


def doc_page(path: str, source: pathlib.Path, title: str, description: str, lead: str = "",
             aside: str = "") -> None:
    crumbs, structured = "", ""
    if path.startswith("/docs/") and path != "/docs/":
        # Shown on the page and described for search with the same two steps
        # (developers.google.com/search/docs/appearance/structured-data/breadcrumb).
        crumbs = (f'<nav class="crumbs" aria-label="Breadcrumb"><a href="/docs/">Docs</a> '
                  f'<span aria-hidden="true">&rsaquo;</span> <span aria-current="page">{html.escape(title)}</span></nav>')
        structured = jsonld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Docs", "item": f"{S['url']}/docs/"},
            {"@type": "ListItem", "position": 2, "name": title}]})
    body = prose(title, markdown(source.read_text(encoding="utf-8")), lead)
    if crumbs:
        body = body.replace('<article class="prose">', f'<article class="prose">{crumbs}', 1)
    if aside:
        body = f'<div class="doc-layout"><nav class="doc-nav" aria-label="Documentation">{aside}</nav>{body}</div>'
    og = OG_DOCS if path.startswith("/docs/") else None
    page(path, title, body, description, og=og, structured=structured)


# ------------------------------------------------------------------ releases ---

# Releases up to 0.2.0-beta.1 named their files with the PEP 440 spelling
# (routemap-0.2.0b1-...); from 0.2.0-beta.2 on, with the tag's own.
PEP440_FILE_NAMES = (0, 2, 0, "b", 1)


def version_for(tag: str) -> str:
    """The spelling a release's file names use: 'v0.2.0-beta.2' -> '0.2.0-beta.2';
    'v0.1.0-beta.4' -> '0.1.0b4' for the releases before the change."""
    m = re.match(r"^v?(\d+\.\d+\.\d+)(?:-(alpha|beta|rc)\.(\d+))?$", tag)
    if not m:
        return tag.lstrip("v")
    order = {"alpha": "a", "beta": "b", "rc": "rc", None: "z"}  # z: a final release sorts last
    key = (*map(int, m.group(1).split(".")), order[m.group(2)], int(m.group(3) or 0))
    if key > PEP440_FILE_NAMES:
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
        # Release files go through this site's /dl/, which answers with a redirect
        # to the same file on GitHub and counts the download (no address kept).
        self.base = f"/dl/{tag}"
        self.sizes: dict[str, int] = {}
        self.date = ""
        self.published = ""
        if release_json:
            data = json.loads(pathlib.Path(release_json).read_text(encoding="utf-8"))
            self.sizes = {a["name"]: int(a["size"]) for a in data.get("assets", [])}
            self.date = (data.get("publishedAt") or "")[:10]
            self.published = data.get("publishedAt") or ""
        self.sums: dict[str, str] = {}
        if sums:
            for line in pathlib.Path(sums).read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) == 2:
                    self.sums[parts[1].lstrip("*")] = parts[0]

    def files(self):
        """(key, group, label, name, note, size, sha) for each file the release has.
        Without the release's file list (a local build), every pattern is listed."""
        import fnmatch
        for key, group, label, pattern, note in PLATFORMS:
            name = pattern.format(v=self.version)
            if self.sizes:
                if "*" in name:
                    name = next((n for n in sorted(self.sizes) if fnmatch.fnmatchcase(n, name)), "")
                if name not in self.sizes:
                    continue  # an earlier release without this format
            else:
                name = name.replace("*", "1")
            yield key, group, label, name, note, self.sizes.get(name), self.sums.get(name)


def size_text(n: int | None) -> str:
    return f"{n / 1_000_000:.0f} MB" if n else ""


PRIMARY = {"windows": ("windows", "Windows"), "macos": ("macos", "macOS"), "linux": ("linux", "Linux")}


def download_buttons(rel: Release) -> str:
    """One button for the visitor's platform, the others one line below.
    site.js marks the platform on <html>; the stylesheet shows the matching
    button. Without JavaScript (or an unknown platform) the button leads to the
    download page and every platform is listed on the line below."""
    files = {key: (group, label, name, size) for key, group, label, name, _n, size, _s in rel.files()}
    buttons = []
    for os_key, (file_key, short) in PRIMARY.items():
        if os_key == "linux":
            # The package depends on the distribution, which the browser does not say.
            buttons.append(f'<a class="dl primary" data-os="linux" href="/download/#linux">Download for Linux</a>')
            continue
        key = file_key if file_key in files else f"{file_key}-zip"
        _group, _label, name, size = files[key]
        extra = f'<span class="size">{size_text(size)}</span>' if size else ""
        buttons.append(f'<a class="dl primary" data-os="{os_key}" href="{rel.base}/{name}">'
                       f"Download for {short}{extra}</a>")
    buttons.append('<a class="dl primary generic" href="/download/">Download</a>')
    others = " ".join(f'<a href="{rel.base}/{name}">{GROUPS[group]} {label}</a>'
                      for key, (group, label, name, _size) in files.items())
    return (f'<div class="downloads">{"".join(buttons)}</div>'
            f'<p class="dl-more">Also: {others}. {html.escape(rel.tag)}, '
            f'<a href="/download/">checksums and install steps</a>.</p>')


# --------------------------------------------------------------------- pages ---

def build_home(rel: Release) -> None:
    body = content("home.html").replace("{{downloads}}", download_buttons(rel)) \
                               .replace("{{tag}}", html.escape(rel.tag))
    page("/", S["product"], body, S["description"], wide=True,
         structured=jsonld(software(rel, "Windows, macOS, Linux"),
                           {"@context": "https://schema.org", **organization()}))


def build_download(rel: Release) -> None:
    rows, seen = [], set()
    for key, group, label, name, note, size, sha in rel.files():
        if group not in seen:
            seen.add(group)
            rows.append(f'<tr class="group" id="{group}"><th scope="rowgroup" colspan="3">{GROUPS[group]}</th></tr>')
        rows.append(f'<tr><th scope="row">{label}<span class="note">{note}</span></th>'
                    f'<td><a href="{rel.base}/{name}">{name}</a>'
                    + (f'<code class="sha">{sha}</code>' if sha else "")
                    + f'</td><td class="num">{size_text(size)}</td></tr>')
    windows_note = ("<p>The Windows build is code-signed with the maintainer's Certum code signing "
                    "certificate.</p>"
                    if SIGNED else content("download-unsigned.html"))
    published = f", published {rel.date}" if rel.date else ""
    win_name = next(f[3] for f in rel.files() if f[1] == "windows")
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
<h2 id="install">Install, upgrade, uninstall</h2>
{content("download-install.html")}
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
<p>On Windows, compare <code>Get-FileHash .\\{html.escape(win_name)}</code> in PowerShell with
its line in <code>SHA256SUMS</code>.</p>
</article>"""
    page("/download/", "Download", body,
         f"Download {S['product']} {rel.tag} for Windows, macOS and Linux from GitHub Releases: "
         "Windows installer, macOS DMG, Linux .deb, .rpm and AppImage, with SHA-256 checksums "
         "signed by the release key.",
         og=OG_DOWNLOAD,
         structured=jsonld(software(rel, "Windows 10, Windows 11, macOS 12 or later, Linux (x86_64)")))


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
    verify = (f'<p class="small">Verify: <code>gpg --verify addresses.txt.asc addresses.txt</code> after '
              f'importing the <a href="/release-key.asc">release key</a>; it must report a good signature '
              f'from <code>{FPR_SPACED}</code>.</p>' if asc else "")
    return f"""<p class="lead">Donations pay for {html.escape(D['pays_for'])}.</p>
<ul class="pay-list">{links}</ul>
<div class="coins">{coins}</div>
<p class="small">The addresses as text: <a href="/donate/addresses.txt">addresses.txt</a>, and {signed}
(<a href="/release-key.asc">key</a> <code>{FPR_SPACED}</code>). Compare the address in your
wallet with this page and the signed file before you send.</p>
{verify}"""


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
              "What Route Map does not do, or does not do yet.",
              "Installing a beta, what to try, and how to report what you found.",
              "Hops, round-trip times and stars: what each line of a traceroute means."]
    index = "".join(f'<li><a href="{p}">{t}</a><span>{b}</span></li>'
                    for (p, _f, t), b in zip(DOC_PAGES, blurbs))
    page("/docs/", "Docs", prose("Documentation", f'<ul class="doc-index">{index}</ul>'),
         f"{S['product']} documentation: user guide, command line, questions, troubleshooting, limitations "
         "and testing a beta.", og=OG_DOCS)
    descriptions = {
        "guide.md": f"How to install and use {S['product']}: first trace, source labels, exports, paste mode, settings and RIPE Atlas.",
        "cli.md": f"{S['product']} command-line reference: commands, options, exit codes and examples.",
        "faq.md": f"Questions about {S['product']}: warnings, cost, sources, privacy, pasted traces.",
        "troubleshooting.md": f"Fixing common {S['product']} problems: Defender, Gatekeeper, missing traceroute, VPN origin.",
        "limitations.md": f"Known limitations of {S['product']}: unsigned builds, IP database hints, what traceroute cannot see.",
        "testing.md": f"Testing a {S['product']} beta: which file to install, what to try, how to report it.",
        "reading-a-traceroute.md": "What each line of a traceroute means.",
    }
    for path, name, title in DOC_PAGES:
        doc_page(path, ROOT / "docs" / name, title, descriptions[name], aside=doc_nav(path))


def build_static_pages(rel: Release) -> None:
    page("/screenshots/", "Screenshots", content("screenshots.html"),
         f"Screenshots of {S['product']} {rel.tag}: light and dark, macOS and Windows, PNG and PDF exports.",
         wide=True)
    page("/compare/", "Compared with paid tools", content("compare.html"),
         "How Route Map differs from paid visual traceroute tools.")
    page("/about/", "About", prose(f"About {S['product']}", content("about.html")),
         f"Who builds {S['product']} and why: OSINTPH, the FalconEye Route Map tab, and how to get in touch.")
    page("/privacy/", "Privacy",
         prose("Privacy", markdown((ROOT / "PRIVACY.md").read_text(encoding="utf-8")) + content("privacy-site.html"),
               content("privacy-lead.html")),
         f"What the {S['product']} app sends, to whom and when (no telemetry), and what this website "
         "records: visits and downloads" + (", and Google Analytics only with your consent." if GA_ID else "."))
    doc_page("/code-signing/", ROOT / "CODE_SIGNING_POLICY.md", "Code signing policy",
             f"How {S['product']} Windows releases are code-signed, and by whom.")
    changelog = markdown((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    changelog = re.sub(r"<p>All notable changes.*?</p>", "", changelog, flags=re.S)
    changelog = re.sub(r'<h2 id="unreleased">Unreleased</h2>\s*', "", changelog)
    page("/changelog/", "Changelog", prose("Changelog", changelog,
         f'Every release, newest first. Downloads: <a href="{L["releases"]}">GitHub Releases</a>.'),
         f"What changed in each {S['product']} release.")
    page("/404", "Not found", prose("Not found", content("404.html")), "Page not found.")


# Each indexable page and the files its content comes from, for the sitemap's
# lastmod: Google uses it only when it is "consistently and verifiably
# accurate", the date of the last significant change to the page's content
# (developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap).
# Template changes (this file, the stylesheet) are not content changes.
PAGE_SOURCES = {
    "/": ["site/content/home.html", "site/site.toml", "site/assets/img"],
    "/download/": ["site/content/download-install.html", "site/content/download-unsigned.html",
                   "site/content/download-firststart.html"],
    "/screenshots/": ["site/content/screenshots.html", "site/assets/img"],
    "/docs/": ["docs/guide.md", "docs/cli.md", "docs/faq.md", "docs/troubleshooting.md",
               "docs/limitations.md", "docs/testing.md", "docs/reading-a-traceroute.md"],
    "/docs/guide/": ["docs/guide.md"], "/docs/cli/": ["docs/cli.md"], "/docs/faq/": ["docs/faq.md"],
    "/docs/troubleshooting/": ["docs/troubleshooting.md"], "/docs/limitations/": ["docs/limitations.md"],
    "/docs/testing/": ["docs/testing.md"], "/docs/reading-a-traceroute/": ["docs/reading-a-traceroute.md"],
    "/compare/": ["site/content/compare.html"],
    "/changelog/": ["CHANGELOG.md"], "/privacy/": ["PRIVACY.md", "site/content/privacy-site.html",
                                                  "site/content/privacy-lead.html"],
    "/code-signing/": ["CODE_SIGNING_POLICY.md"], "/about/": ["site/content/about.html"],
    "/support/": ["site/content/support.html", "site/donate"], "/donate/": ["site/donate"],
}


def lastmod(page_path: str, release_date: str = "") -> str:
    """The last commit date of the page's sources (with the release date for the
    download page), or "" when the history is not there to say (a shallow clone)."""
    import subprocess
    shallow = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--is-shallow-repository"],
                             capture_output=True, text=True)
    if shallow.returncode != 0 or shallow.stdout.strip() != "false":
        return ""
    out = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%cI", "--",
                          *PAGE_SOURCES[page_path]], capture_output=True, text=True).stdout.strip()
    dates = [d for d in (out, release_date) if d]
    return max(dates, key=lambda d: d[:10]) if dates else ""


def build_files(release: "Release") -> None:
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
    missing = sorted(set(pages) - set(PAGE_SOURCES))
    if missing:
        raise SystemExit(f"pages without PAGE_SOURCES (the sitemap's lastmod): {missing}")
    def entry(p: str) -> str:
        when = lastmod(p, release.published if p == "/download/" else "")
        return f"  <url><loc>{S['url']}{p}</loc>" + (f"<lastmod>{when}</lastmod>" if when else "") + "</url>\n"
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(entry(p) for p in pages) + "</urlset>\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default=tag_for(__version__))
    parser.add_argument("--release-json")
    parser.add_argument("--sums")
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--ga-id", help="a Google Analytics measurement ID in place of site.toml's (tests)")
    args = parser.parse_args(argv)
    global GA_ID
    if args.ga_id is not None:
        if args.ga_id and not re.fullmatch(r"G-[A-Z0-9]{4,20}", args.ga_id):
            raise SystemExit(f"--ga-id {args.ga_id!r} is not a G- measurement ID")
        GA_ID = args.ga_id
    OUT = pathlib.Path(args.out)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copytree(SITE / "assets", OUT / "assets")
    global LATEST  # noqa: PLW0603
    import hashlib
    for name in ("style.css", "site.js", "consent.js"):
        ASSET_VERSION[name] = hashlib.sha256((SITE / "assets" / name).read_bytes()).hexdigest()[:10]
    # Font URLs in the built stylesheet carry their content hash, as images do:
    # a re-subset font keeps its name, and Cloudflare kept serving the old one.
    css_out = OUT / "assets" / "style.css"
    css = re.sub(r'url\("(/assets/fonts/[^"?]+)"\)', lambda m: f'url("{img_url(m.group(1))}")',
                 css_out.read_text(encoding="utf-8"))
    css_out.write_text(css, encoding="utf-8")
    ASSET_VERSION["style.css"] = hashlib.sha256(css.encode("utf-8")).hexdigest()[:10]
    rel = Release(args.tag, args.release_json, args.sums)
    LATEST = rel.tag
    build_home(rel)
    build_download(rel)
    build_support()
    build_docs()
    build_static_pages(rel)
    build_files(rel)
    count = sum(1 for _ in OUT.rglob("*.html"))
    print(f"{count} pages in {OUT} for {rel.tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
