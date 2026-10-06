"""Google Analytics on the site, in a real browser (headless Chrome through
Playwright): nothing from Google before consent or after a refusal, Analytics
and the download event after consent, and withdrawal removes its cookies.

Needs Playwright and Google Chrome; skipped without them. Google is never
contacted: gtag.js is answered by a local stub that only records it was asked
for, and every other outside request is refused and recorded.
"""
import functools
import http.server
import pathlib
import subprocess
import sys
import threading

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")

ROOT = pathlib.Path(__file__).resolve().parents[1]
GA_ID = "G-TEST1234"
GOOGLE = ("googletagmanager.com", "google-analytics.com", "analytics.google.com", "doubleclick.net",
          "google.com")

STUB = """
window.__gtagStub = (window.__gtagStub || 0) + 1;
document.cookie = "_ga=GA1.1.111.222; Path=/; SameSite=Lax";
document.cookie = "_ga_TEST1234=GS1.1.333; Path=/; SameSite=Lax";
"""


def _build(out: pathlib.Path, ga_id: str) -> pathlib.Path:
    subprocess.run([sys.executable, str(ROOT / "site" / "build.py"), "--out", str(out),
                    "--tag", "v0.2.0-beta.5", "--ga-id", ga_id], check=True, capture_output=True)
    return out


# The policy the site's server sends with every page (its nginx config, kept
# outside this repository): consent.js and gtag.js must work under it.
CSP = ("default-src 'none'; img-src 'self' https://www.googletagmanager.com https://*.google-analytics.com "
       "https://*.google.com https://*.g.doubleclick.net; style-src 'self'; font-src 'self'; "
       "script-src 'self' https://static.cloudflareinsights.com https://www.googletagmanager.com; "
       "connect-src 'self' https://cloudflareinsights.com https://www.googletagmanager.com "
       "https://*.google-analytics.com https://*.google.com https://*.g.doubleclick.net "
       "https://pagead2.googlesyndication.com; frame-src https://www.googletagmanager.com; "
       "manifest-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        super().end_headers()

    def log_message(self, *args):
        pass


def _serve(folder: pathlib.Path):
    handler = functools.partial(_Quiet, directory=str(folder))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://localhost:{server.server_address[1]}"


@pytest.fixture(scope="module")
def sites(tmp_path_factory):
    on = _build(tmp_path_factory.mktemp("on"), GA_ID)
    off = _build(tmp_path_factory.mktemp("off"), "")
    s_on, url_on = _serve(on)
    s_off, url_off = _serve(off)
    yield {"on": url_on, "off": url_off}
    s_on.shutdown()
    s_off.shutdown()


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Google Chrome not available: {exc}")
        yield b
        b.close()


class Visit:
    """A fresh browser profile that records every request leaving localhost."""

    def __init__(self, browser, javascript=True):
        self.ctx = browser.new_context(java_script_enabled=javascript)
        self.outside, self.dl = [], []
        self.ctx.route("**/*", self._route)
        self.page = self.ctx.new_page()
        self.csp = []
        self.page.on("console", lambda m: self.csp.append(m.text) if "Content Security Policy" in m.text else None)

    def _route(self, route):
        url = route.request.url
        if url.startswith("http://localhost:") or url.startswith("http://127.0.0.1:"):
            if "/dl/" in url:
                self.dl.append(url)
                return route.fulfill(status=204, body="")
            return route.continue_()
        self.outside.append(url)
        if url.startswith("https://www.googletagmanager.com/gtag/js"):
            return route.fulfill(status=200, content_type="application/javascript", body=STUB)
        return route.abort()

    def wait_for_stub(self, count=1):
        """Polls from outside the page: wait_for_function evaluates a string,
        which the site's policy (rightly) refuses."""
        for _ in range(50):
            if self.page.evaluate("window.__gtagStub || 0") == count:
                return
            self.page.wait_for_timeout(100)
        raise AssertionError("gtag.js was not loaded")

    def google(self):
        return [u for u in self.outside if any(g in u for g in GOOGLE)]

    def cookies(self):
        return [c["name"] for c in self.ctx.cookies()]

    def close(self):
        self.ctx.close()


@pytest.fixture
def visit(browser):
    made = []

    def make(**kw):
        v = Visit(browser, **kw)
        made.append(v)
        return v
    yield make
    for v in made:
        v.close()


PAGES = ["/", "/download/", "/docs/", "/privacy/"]


def test_nothing_from_google_before_a_choice(sites, visit):
    v = visit()
    for path in PAGES:
        v.page.goto(sites["on"] + path)
        v.page.wait_for_load_state("networkidle")
        assert v.page.locator("#consent").is_visible()
        if path == "/download/":
            v.page.locator('a[href^="/dl/"]:visible').first.click()
    assert v.google() == [] and v.cookies() == []
    assert v.page.evaluate("typeof window.gtag") == "undefined"


def test_accept_and_reject_are_equally_prominent(sites, visit):
    v = visit()
    v.page.goto(sites["on"] + "/")
    accept = v.page.locator('[data-consent="granted"]')
    reject = v.page.locator('[data-consent="denied"]')
    a, r = accept.bounding_box(), reject.bounding_box()
    assert accept.get_attribute("class") == reject.get_attribute("class") == "consent-button"
    assert abs(a["height"] - r["height"]) < 1 and abs(a["y"] - r["y"]) < 1, "same size, same row"
    style = "e => [getComputedStyle(e).backgroundColor, getComputedStyle(e).color, getComputedStyle(e).fontWeight]"
    assert accept.evaluate(style) == reject.evaluate(style)


def test_reject_loads_nothing_now_or_later(sites, visit):
    v = visit()
    v.page.goto(sites["on"] + "/")
    v.page.click('[data-consent="denied"]')
    for path in PAGES:
        v.page.goto(sites["on"] + path)
        v.page.wait_for_load_state("networkidle")
        assert not v.page.locator("#consent").is_visible(), "the choice is remembered"
    v.page.goto(sites["on"] + "/download/")
    v.page.locator('a[href^="/dl/"]:visible').first.click()
    v.page.wait_for_timeout(300)
    assert v.google() == [] and v.cookies() == []
    assert v.page.evaluate("localStorage.getItem('analytics-consent')") == "denied"


def test_accept_loads_analytics_and_download_clicks_are_events(sites, visit):
    v = visit()
    v.page.goto(sites["on"] + "/download/")
    v.page.click('[data-consent="granted"]')
    v.wait_for_stub()
    assert v.google() == [f"https://www.googletagmanager.com/gtag/js?id={GA_ID}"]
    layer = v.page.evaluate("window.dataLayer.map(a => Array.from(a))")
    assert layer[0][0] == "js" and layer[1] == ["config", GA_ID]
    v.page.locator('a[href$="-windows-x86_64-setup.exe"]:visible').first.click()
    v.page.wait_for_timeout(200)
    events = v.page.evaluate("""(window.dataLayer || []).filter(a => a[0] === 'event').map(a => [a[1], a[2]])""")
    assert events == [["routemap_download", {"file": "routemap-0.2.0-beta.5-windows-x86_64-setup.exe",
                                             "platform": "windows", "version": "0.2.0-beta.5"}]]
    assert v.dl == [sites["on"] + "/dl/v0.2.0-beta.5/routemap-0.2.0-beta.5-windows-x86_64-setup.exe"]
    assert v.csp == [], "consent.js and gtag.js run under the site's policy"
    v.page.locator('a[href$="/SHA256SUMS"]:visible').first.click()
    v.page.wait_for_timeout(200)
    last = v.page.evaluate("(window.dataLayer || []).filter(a => a[0] === 'event').pop()[2]")
    assert last == {"file": "SHA256SUMS", "platform": "checksums", "version": "0.2.0-beta.5"}


def test_consent_is_remembered_across_pages(sites, visit):
    v = visit()
    v.page.goto(sites["on"] + "/")
    v.page.click('[data-consent="granted"]')
    v.page.goto(sites["on"] + "/docs/")
    v.wait_for_stub()
    assert not v.page.locator("#consent").is_visible()


def test_withdrawing_consent_deletes_the_cookies_and_stops_analytics(sites, visit):
    v = visit()
    v.page.goto(sites["on"] + "/")
    v.page.click('[data-consent="granted"]')
    v.wait_for_stub()
    assert {"_ga", "_ga_TEST1234"} <= set(v.cookies())
    v.page.click("#cookie-settings")
    assert v.page.locator("#consent").is_visible()
    asked = len(v.google())
    with v.page.expect_navigation():
        v.page.click('[data-consent="denied"]')
    v.page.wait_for_load_state("networkidle")
    assert [c for c in v.cookies() if c.startswith("_ga")] == []
    assert v.page.evaluate("typeof window.gtag") == "undefined"
    v.page.goto(sites["on"] + "/download/")
    v.page.locator('a[href^="/dl/"]:visible').first.click()
    v.page.wait_for_timeout(300)
    assert len(v.google()) == asked, "nothing more from Google after withdrawal"


def test_privacy_page_link_reopens_the_choice(sites, visit):
    v = visit()
    v.page.goto(sites["on"] + "/privacy/")
    v.page.click('[data-consent="denied"]')
    v.page.click('#google-analytics ~ ul [data-cookie-settings]')
    assert v.page.locator("#consent").is_visible()


def test_without_javascript_nothing_loads_and_nothing_is_asked(sites, visit):
    v = visit(javascript=False)
    for path in PAGES:
        v.page.goto(sites["on"] + path)
        assert not v.page.locator("#consent").is_visible()
    assert v.google() == [] and v.cookies() == []


def test_without_a_measurement_id_there_is_no_banner_and_no_script(sites, visit):
    v = visit()
    for path in PAGES:
        v.page.goto(sites["off"] + path)
        v.page.wait_for_load_state("networkidle")
        assert v.page.locator("#consent").count() == 0
        assert v.page.locator('script[src*="consent.js"]').count() == 0
        assert v.page.locator("#cookie-settings").count() == 0
    assert v.google() == []
