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
        assert scripts == ['<script src="/assets/site.js">'], (page, scripts)
        assert chr(0x2014) not in text, f"em dash in {page}"
        # Assets (src= and stylesheet/icon links) only from this site.
        for url in re.findall(r'src="([^"]+)"', text) + re.findall(r'<link[^>]+href="([^"]+)"', text):
            assert url.startswith("/") or url.startswith("https://getroutemap.app"), (page, url)
        for href in re.findall(r'<a href="(/[^"#]*)', text):
            if href == "/":
                continue
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
