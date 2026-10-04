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
        scripts = re.findall(r"<script[^>]*>", text, flags=re.I)
        assert len(scripts) == 1 and re.fullmatch(r'<script src="/assets/site\.js\?v=[0-9a-f]{10}">', scripts[0]), (page, scripts)
        # Stylesheet and script are cache-busted by content hash.
        assert re.search(r'href="/assets/style\.css\?v=[0-9a-f]{10}"', text), page
        assert chr(0x2014) not in text, f"em dash in {page}"
        # Assets (src= and stylesheet/icon links) only from this site.
        for url in re.findall(r'src="([^"]+)"', text) + re.findall(r'<link[^>]+href="([^"]+)"', text):
            assert url.startswith("/") or url.startswith("https://getroutemap.app"), (page, url)
        for href in re.findall(r'<a href="(/[^"#]*)', text):
            if href == "/":
                continue
            href = href.split("?", 1)[0]
            name = href.rstrip("/").rsplit("/", 1)[-1]
            target = out / href.lstrip("/") if "." in name else out / href.strip("/") / "index.html"
            assert target.exists(), (page, href)
    js = (ROOT / "site" / "assets" / "site.js").read_text(encoding="utf-8")
    for call in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "document.cookie", "import("):
        assert call not in js, f"site.js must not use {call}"
    download = (out / "download" / "index.html").read_text(encoding="utf-8")
    assert "releases/download/v0.1.0-beta.4/routemap-0.1.0b4-windows-x86_64.zip" in download
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
        urls |= set(re.findall(r'(?:src|srcset)="(/assets/img/[^"]+)"', page.read_text(encoding="utf-8")))
    assert urls, "no screenshots found"
    bare = sorted(u for u in urls if "?v=" not in u)
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
             "routemap_0.2.0~beta.2-57_amd64.deb", "routemap-0.2.0~beta.2-57.x86_64.rpm",
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
    assert f'data-os="windows" href="https://github.com/osintph/routemap/releases/download/{tag}/{names[0]}"' in page
    assert "Install for me only" in page and "Settings &gt; Apps" in page
    old = subprocess.run([sys.executable, str(ROOT / "site" / "build.py"), "--out", str(tmp_path / "old"),
                          "--tag", "v0.2.0-beta.1"], capture_output=True, text=True)
    assert old.returncode == 0, old.stderr
    assert "routemap-0.2.0b1-windows-x86_64.zip" in (tmp_path / "old" / "download" / "index.html").read_text()
