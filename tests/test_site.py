"""The project site (site/build.py) keeps its promises: no scripts, no external
assets, no cookies, no em dashes, and no broken internal links."""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_site_builds_without_scripts_or_external_assets_and_links_resolve(tmp_path):
    out = tmp_path / "site"
    run = subprocess.run([sys.executable, str(ROOT / "site" / "build.py"), "--out", str(out),
                          "--tag", "v0.1.0-beta.4"], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    pages = list(out.rglob("*.html"))
    assert len(pages) >= 10
    for page in pages:
        text = page.read_text(encoding="utf-8")
        # One script, from this site, never inline: the platform mark and the theme switch.
        # (JSON-LD blocks are data for search engines, not scripts that run.)
        scripts = [t for t in re.findall(r"<script[^>]*>", text, flags=re.I) if "application/ld+json" not in t]
        assert len(scripts) == 1 and re.fullmatch(r'<script src="/assets/site\.js\?v=[0-9a-f]{10}">', scripts[0]), (page, scripts)
        # Stylesheet and script are cache-busted by content hash.
        assert re.search(r'href="/assets/style\.css\?v=[0-9a-f]{10}"', text), page
        assert chr(0x2014) not in text, f"em dash in {page}"
        # Assets (src= and stylesheet/icon links) only from this site.
        for url in re.findall(r'src="([^"]+)"', text) + re.findall(r'<link[^>]+href="([^"]+)"', text):
            assert url.startswith("/") or url.startswith("https://getroutemap.app"), (page, url)
        for href in re.findall(r'<a href="(/[^"#]*)', text):
            if href == "/" or href.startswith("/dl/"):
                continue  # /dl/ is a redirect the server answers, not a file
            href = href.split("?", 1)[0]
            name = href.rstrip("/").rsplit("/", 1)[-1]
            target = out / href.lstrip("/") if "." in name else out / href.strip("/") / "index.html"
            assert target.exists(), (page, href)
    js = (ROOT / "site" / "assets" / "site.js").read_text(encoding="utf-8")
    for call in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "document.cookie", "import("):
        assert call not in js, f"site.js must not use {call}"
    download = (out / "download" / "index.html").read_text(encoding="utf-8")
    assert 'href="/dl/v0.1.0-beta.4/routemap-0.1.0b4-windows-x86_64.zip"' in download
    assert "releases/download/" not in download, "file links go through /dl/"
    assert "D57C 7E26" in download and "Run anyway" in download
    home = (out / "index.html").read_text(encoding="utf-8")
    for page_text in (home, (out / "screenshots" / "index.html").read_text(encoding="utf-8")):
        assert "[[pic" not in page_text
    assert home.count('data-scheme="dark"') >= 5, "screenshots must come as light and dark pairs"
    assert "support@getroutemap.app" in home and "Latest release" in home
    assert (out / ".well-known" / "security.txt").read_text().startswith("Contact: mailto:support@getroutemap.app")
    assert (out / "donate" / "addresses.txt").exists()
    assert "sponsors" not in home.lower()
    assert (out / "robots.txt").exists() and (out / "404.html").exists()


def test_every_screenshot_url_carries_its_content_hash(tmp_path):
    """Retaken screenshots keep their names; without a hash in the URL,
    Cloudflare served the previous release's images after a deploy."""
    import re
    import subprocess
    import sys
    root = pathlib.Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "site" / "build.py"), "--out", str(tmp_path)], check=True,
                   capture_output=True)
    urls = set()
    for page in tmp_path.rglob("*.html"):
        for attr in re.findall(r'(?:src|srcset)="(/assets/img/[^"]+)"', page.read_text(encoding="utf-8")):
            urls |= {u.strip().split(" ")[0] for u in attr.split(",")}
    assert urls, "no screenshots found"
    # Either a ?v= query or, for the generated sizes and formats, the hash in the name.
    bare = sorted(u for u in urls if "?v=" not in u and not re.search(r"-[0-9a-f]{10}-\d+\.\w+$", u))
    assert not bare, bare


BANNED_FONTS = ("Inter", "Geist", "Space Grotesk", "Plus Jakarta Sans", "DM Sans", "Manrope", "Outfit",
                "Poppins", "Satoshi", "General Sans", "Archivo")
FONT_SERVICES = ("fonts.googleapis.com", "fonts.gstatic.com", "use.typekit.net", "fonts.bunny.net",
                 "fontshare.com", "cdnfonts.com", "fonts.adobe.com")


def _built(tmp_path):
    out = tmp_path / "site"
    subprocess.run([sys.executable, str(ROOT / "site" / "build.py"), "--out", str(out)], check=True,
                   capture_output=True)
    return out


def test_no_banned_font_and_no_font_service(tmp_path):
    """site/README.md lists the fonts this site must not use; and no page or
    stylesheet may load fonts from another server (a visitor's address would
    go there)."""
    out = _built(tmp_path)
    texts = [(f, f.read_text(encoding="utf-8")) for f in list(out.rglob("*.html")) + list(out.rglob("*.css"))]
    for path, text in texts:
        for family in BANNED_FONTS:
            assert not re.search(rf"""["']{re.escape(family)}["']""", text), f"{family} in {path.name}"
        for host in FONT_SERVICES:
            assert host not in text, f"{host} in {path.name}"
    css = (out / "assets" / "style.css").read_text(encoding="utf-8")
    assert re.search(r"h1, h2, h3 \{ font-family: var\(--display\)", css)
    body = re.search(r"body \{[^}]*\}", css).group(0)
    assert "var(--text)" in body and "--mono" not in body, "monospace only for code, commands and tables"


def test_the_fonts_cover_every_character_the_site_shows(tmp_path):
    pytest = __import__("pytest")
    ttlib = pytest.importorskip("fontTools.ttLib")
    pytest.importorskip("brotli")
    import html as _html
    out = _built(tmp_path)
    used = set()
    for page in out.rglob("*.html"):
        text = re.sub(r"<script.*?</script>|<style.*?</style>", "", page.read_text(encoding="utf-8"), flags=re.S)
        used |= set(_html.unescape(re.sub(r"<[^>]+>", " ", text)))
    used -= set("\n\r\t")
    fonts = ROOT / "site" / "assets" / "fonts"
    for name in ("newsreader-var.woff2", "schibsted-grotesk-var.woff2", "plex-mono-regular.woff2"):
        cmap = ttlib.TTFont(fonts / name).getBestCmap()
        missing = sorted(c for c in used if ord(c) not in cmap)
        assert not missing, f"{name} lacks {missing}: re-subset it (site/README.md, Typography)"



def test_font_urls_carry_their_content_hash(tmp_path):
    """A re-subset font keeps its file name; without a hash in the URL the CDN
    kept serving the previous file (4 Oct 2026)."""
    out = _built(tmp_path)
    css = (out / "assets" / "style.css").read_text(encoding="utf-8")
    urls = re.findall(r'url\("(/assets/fonts/[^"]+)"\)', css)
    assert urls and all("?v=" in u for u in urls), urls
    home = (out / "index.html").read_text(encoding="utf-8")
    for pre in re.findall(r'rel="preload" href="([^"]+)"', home):
        assert pre in urls, f"preload {pre} must match the stylesheet's URL exactly"


def test_the_download_page_puts_the_installer_first_for_each_platform(tmp_path):
    """From 0.2.0-beta.2: per platform the installer row comes first, the
    package names (with their build number) come from the release's file list,
    and the Windows button downloads the installer."""
    import json
    v, tag = "0.2.0-beta.2", "v0.2.0-beta.2"
    names = [f"routemap-{v}-windows-x86_64-setup.exe", f"routemap-{v}-windows-x86_64.zip",
             f"routemap-{v}-macos-arm64.dmg", f"routemap-{v}-macos-x86_64.dmg",
             f"routemap-{v}-linux-x86_64.deb", f"routemap-{v}-linux-x86_64.rpm",
             f"routemap-{v}-linux-x86_64.AppImage", f"routemap-{v}-linux-x86_64.tar.gz", "SHA256SUMS"]
    rel = tmp_path / "release.json"
    rel.write_text(json.dumps({"tagName": tag, "publishedAt": "2026-10-05T00:00:00Z",
                               "assets": [{"name": n, "size": 1_000_000} for n in names]}))
    out = tmp_path / "site"
    subprocess.run([sys.executable, str(ROOT / "site" / "build.py"), "--out", str(out), "--tag", tag,
                    "--release-json", str(rel)], check=True, capture_output=True)
    page = (out / "download" / "index.html").read_text(encoding="utf-8")
    order = [page.index(n) for n in names[:8]]
    assert order[0] < order[1] and order[4] < order[6], "installer before zip, packages before AppImage"
    assert 'id="windows"' in page and 'id="macos"' in page and 'id="linux"' in page
    assert f'data-os="windows" href="/dl/{tag}/{names[0]}"' in page
    assert "Install for me only" in page and "Settings &gt; Apps" in page
    old = subprocess.run([sys.executable, str(ROOT / "site" / "build.py"), "--out", str(tmp_path / "old"),
                          "--tag", "v0.2.0-beta.1"], capture_output=True, text=True)
    assert old.returncode == 0, old.stderr
    assert "routemap-0.2.0b1-windows-x86_64.zip" in (tmp_path / "old" / "download" / "index.html").read_text()


# ---------------------------------------------------------------- search ---
# One build with a release's file list, shared by the checks below.

import functools  # noqa: E402
import json as _json  # noqa: E402


@functools.lru_cache(maxsize=1)
def _built(tmp=None) -> pathlib.Path:
    import tempfile
    out = pathlib.Path(tempfile.mkdtemp()) / "site"
    v, tag = "0.2.0-beta.2", "v0.2.0-beta.2"
    names = [f"routemap-{v}-windows-x86_64-setup.exe", f"routemap-{v}-windows-x86_64.zip",
             f"routemap-{v}-macos-arm64.dmg", f"routemap-{v}-macos-x86_64.dmg",
             f"routemap-{v}-linux-x86_64.deb", f"routemap-{v}-linux-x86_64.rpm",
             f"routemap-{v}-linux-x86_64.AppImage", f"routemap-{v}-linux-x86_64.tar.gz"]
    rel = out.parent / "release.json"
    rel.write_text(_json.dumps({"tagName": tag, "publishedAt": "2026-10-05T00:29:00Z",
                                "assets": [{"name": n, "size": 1_000_000} for n in names]}))
    subprocess.run([sys.executable, str(ROOT / "site" / "build.py"), "--out", str(out), "--tag", tag,
                    "--release-json", str(rel)], check=True, capture_output=True)
    return out


def _ld(page: str) -> list[dict]:
    return [_json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]


def _text(page: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", page, flags=re.S)))


def test_structured_data_states_only_what_the_page_shows():
    out = _built()
    for path, oses in (("index.html", "Windows, macOS, Linux"),
                       ("download/index.html", "Windows 10, Windows 11, macOS 12 or later, Linux (x86_64)")):
        page = (out / path).read_text(encoding="utf-8")
        app = next(o for o in _ld(page) if o["@type"] == "SoftwareApplication")
        assert app["name"] == "Route Map" and app["offers"]["price"] == "0" and app["operatingSystem"] == oses
        assert app["applicationCategory"] == "UtilitiesApplication" and app["publisher"]["name"] == "OSINTPH"
        text = _text(page)
        assert app["softwareVersion"] in text and "OSINTPH" in text and "ree" in text   # Free / free
        assert "aggregateRating" not in app and "review" not in app, "no invented ratings"
    home = _ld((out / "index.html").read_text(encoding="utf-8"))
    assert any(o["@type"] == "Organization" and o["name"] == "OSINTPH" for o in home)
    guide = (out / "docs" / "guide" / "index.html").read_text(encoding="utf-8")
    crumbs = next(o for o in _ld(guide) if o["@type"] == "BreadcrumbList")["itemListElement"]
    assert [c["name"] for c in crumbs] == ["Docs", "User guide"] and crumbs[0]["item"].endswith("/docs/")
    assert 'aria-label="Breadcrumb"' in guide, "the breadcrumb in the markup is also on the page"


def test_every_page_has_its_own_title_description_and_canonical():
    out = _built()
    seen_titles, seen_desc = set(), set()
    for f in sorted(out.rglob("index.html")):
        page = f.read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", page).group(1)
        desc = re.search(r'<meta name="description" content="([^"]*)"', page).group(1)
        assert title not in seen_titles and desc not in seen_desc, f
        seen_titles.add(title); seen_desc.add(desc)
        assert page.count("<h1") == 1, f
        assert re.search(r'<link rel="canonical" href="https://getroutemap\.app/[^"]*">', page), f
    four = (out / "404.html").read_text(encoding="utf-8")
    assert 'rel="canonical"' not in four and 'href="/download/"' in four and 'href="/docs/"' in four


def test_previews_are_1200_by_630_and_exist():
    from PIL import Image
    out = _built()
    for path in ("index.html", "download/index.html", "docs/index.html", "docs/guide/index.html"):
        page = (out / path).read_text(encoding="utf-8")
        url = re.search(r'<meta property="og:image" content="https://getroutemap\.app([^"?]+)', page).group(1)
        assert Image.open(out / url.lstrip("/")).size == (1200, 630), path
        assert re.search(r'<meta name="twitter:image:alt" content="[^"]{20,}"', page), path
    assert "/assets/og/download.jpg" in (out / "download/index.html").read_text(encoding="utf-8")
    assert "/assets/og/docs.jpg" in (out / "docs/index.html").read_text(encoding="utf-8")


def test_screenshots_come_in_modern_formats_with_a_fallback_and_their_files_exist():
    out = _built()
    home = (out / "index.html").read_text(encoding="utf-8")
    pictures = re.findall(r"<picture>.*?</picture>", home, re.S)
    assert pictures
    for pic in pictures:
        assert 'type="image/avif"' in pic and 'type="image/webp"' in pic
        img = re.search(r"<img [^>]+>", pic).group(0)
        assert re.search(r'width="\d+" height="\d+"', img) and 'alt="' in img and "sizes=" in img
        for url in re.findall(r"(/assets/img/v/[^ ,\"]+)", pic):
            assert (out / url.lstrip("/")).exists(), url
    assert pictures[0].count('fetchpriority="high"') == 1 and 'loading="lazy"' not in pictures[0]


def test_links_into_the_repository_keep_dot_folders():
    """The code-signing page linked to github/workflows/build.yml: lstrip("./")
    also removed the dot of ".github"."""
    sys.path.insert(0, str(ROOT / "site"))
    import build
    assert build._link(".github/workflows/build.yml").endswith("/blob/main/.github/workflows/build.yml")
    assert build._link("./docs/guide.md#install") == "/docs/guide/#install"
    page = (_built() / "code-signing" / "index.html").read_text(encoding="utf-8")
    assert "/blob/main/.github/workflows/build.yml" in page and "/blob/main/github/" not in page


def test_sitemap_lists_every_page_with_its_last_content_change():
    out = _built()
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    pages = {"/" if f.parent == out else "/" + f.parent.relative_to(out).as_posix() + "/"
             for f in out.rglob("index.html")}
    locs = set(re.findall(r"<loc>https://getroutemap\.app([^<]+)</loc>", sitemap))
    assert locs == pages
    shallow = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--is-shallow-repository"],
                             capture_output=True, text=True).stdout.strip()
    if shallow == "false":
        sys.path.insert(0, str(ROOT / "site"))
        import build
        # A page gets a date when its sources have history (a new, uncommitted page has none yet).
        with_history = {p for p in locs if subprocess.run(
            ["git", "-C", str(ROOT), "log", "-1", "--format=%cI", "--", *build.PAGE_SOURCES[p]],
            capture_output=True, text=True).stdout.strip()}
        dated = set(re.findall(r"<loc>https://getroutemap\.app([^<]+)</loc><lastmod>", sitemap))
        assert dated == with_history and with_history
        dates = re.findall(r"<lastmod>([^<]+)</lastmod>", sitemap)
        assert all(re.fullmatch(r"\d{4}-\d\d-\d\dT[\d:]+[+-]\d\d:\d\d|\d{4}-\d\d-\d\dT[\d:]+Z", d) for d in dates)
    assert "Sitemap: https://getroutemap.app/sitemap.xml" in (out / "robots.txt").read_text()


def test_no_image_renders_outside_its_figure_or_under_text():
    """A caption pulled up by a negative margin covered the bottom 12 px of the
    home page screenshot (its status bar) at every width. Measured in Chrome at a
    phone width and a 13-inch laptop width, light and dark."""
    import pytest
    sys.path.insert(0, str(ROOT / "site" / "check"))
    import figures
    if not figures.find_chrome():
        pytest.skip("Chrome is not installed")
    problems = figures.check(_built(), widths=(390, 1366), schemes=("light", "dark"))
    assert not problems, "\n".join(problems)


def test_the_readme_and_the_install_page_say_route_map_is_not_on_pypi():
    """RM-15: `pip install routemap` installs someone else's project."""
    root = pathlib.Path(__file__).resolve().parents[1]
    for path in (root / "README.md", root / "site" / "content" / "download-install.html"):
        text = " ".join(path.read_text(encoding="utf-8").split())
        assert "not on PyPI" in text and "pip install routemap" in text, path.name


def _build_site(tmp_path, ga_id):
    out = tmp_path / ("ga" if ga_id else "plain")
    subprocess.run([sys.executable, str(ROOT / "site" / "build.py"), "--out", str(out), "--tag", "v0.2.0-beta.5",
                    "--ga-id", ga_id], check=True, capture_output=True)
    return out


def test_consent_script_only_adds_gtag_and_deletes_its_cookies():
    """consent.js is the only place Google appears; it never sends anything itself."""
    js = (ROOT / "site" / "assets" / "consent.js").read_text(encoding="utf-8")
    for call in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "import(", "eval(", "innerHTML"):
        assert call not in js, call
    assert re.findall(r"https://[^\"' ]+", js) == ["https://www.googletagmanager.com/gtag/js?id="]
    assert js.count('document.cookie = ') == 1 and "Max-Age=0" in js, "cookies are only deleted, never set"


def test_no_google_in_any_page_and_analytics_only_when_configured(tmp_path):
    plain, ga = _build_site(tmp_path, ""), _build_site(tmp_path, "G-TEST1234")
    for page in plain.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        assert "consent.js" not in text and 'id="consent"' not in text and "ga-measurement-id" not in text, page
        assert "google-analytics" not in text and "Google Analytics" not in text, page
    for page in ga.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        assert "googletagmanager" not in text and "gtag(" not in text, page
        assert '<meta name="ga-measurement-id" content="G-TEST1234">' in text, page
        assert text.count('class="consent-button"') == 2 and "data-cookie-settings" in text, page
    privacy_ga = (ga / "privacy" / "index.html").read_text(encoding="utf-8")
    privacy_plain = (plain / "privacy" / "index.html").read_text(encoding="utf-8")
    assert 'id="google-analytics"' in privacy_ga and 'id="google-analytics"' not in privacy_plain
    for text in (privacy_ga, privacy_plain):
        assert "<!--" not in text.split("<main", 1)[1].replace("<!-- ", ""), "no condition markers left"
        assert "sets no cookies; the light" not in text
        assert 'href="https://db-ip.com">IP Geolocation by DB-IP</a>' in text, "CC BY attribution"
        assert "daily visitor hash" in text and "30 days" in text
    assert "policies.google.com/privacy" in privacy_ga
    assert "light or dark choice and your\nAnalytics choice are kept" in privacy_ga
    assert "light or dark choice is kept" in privacy_plain.replace("\n", " ").replace("choice\n is", "choice is")


def test_ga_id_is_checked(tmp_path):
    bad = subprocess.run([sys.executable, str(ROOT / "site" / "build.py"), "--out", str(tmp_path / "x"),
                          "--ga-id", "UA-1234-1"], capture_output=True, text=True)
    assert bad.returncode != 0 and "not a G- measurement ID" in bad.stderr
