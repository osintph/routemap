"""The update check opens nothing but this repository's own release pages and
files, shows text as text, and shows the offered file's SHA-256 with the
command to check it (hardening 9). Its one API answer is read under a cap."""
import asyncio
import os

import httpx
import pytest


from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from routemap import service  # noqa: E402
from routemap.__about__ import REPO_URL  # noqa: E402

PREFIX = REPO_URL + "/"
DIGEST = "ab" * 32
HOSTILE = [
    "file:///C:/Windows/System32/calc.exe",
    "https://evil.example/routemap-0.9.0-macos-arm64.dmg",
    "https://github.com/osintph/routemap.evil/releases/download/v0.9.0/x.dmg",
    "https://github.com/osintph/routemapX/releases/download/v0.9.0/x.dmg",
    "http://github.com/osintph/routemap/releases/download/v0.9.0/x.dmg",
    "\\\\attacker\\share\\x.dmg",
    "https://github.com/osintph/routemap/%2e%2e/%2E%2E/evil/x.dmg",
]


def _answer(page, assets, tag="v0.9.0"):
    return [{"tag_name": tag, "html_url": page,
             "assets": [{"name": n, "browser_download_url": u, "digest": f"sha256:{DIGEST}"} for n, u in assets]}]


def _latest(body, monkeypatch):
    real = httpx.AsyncClient

    def mock(*a, **k):
        k["transport"] = httpx.MockTransport(lambda r: httpx.Response(200, **body))
        return real(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", mock)
    return asyncio.run(service.latest_release())


def test_only_this_repositorys_release_urls_survive(monkeypatch):
    good = f"{REPO_URL}/releases/download/v0.9.0/routemap-0.9.0-macos-arm64.dmg"
    assets = [(f"routemap-0.9.0-macos-arm64-{i}.dmg", u) for i, u in enumerate(HOSTILE)] + \
             [("routemap-0.9.0-macos-arm64.dmg", good)]
    for page in HOSTILE:
        latest = _latest({"json": _answer(page, assets)}, monkeypatch)
        assert latest["page"] == f"{REPO_URL}/releases"
        assert latest["assets"] == {"routemap-0.9.0-macos-arm64.dmg": good}
        assert latest["digests"] == {"routemap-0.9.0-macos-arm64.dmg": DIGEST}


def test_a_tag_that_is_not_a_release_tag_is_no_release(monkeypatch):
    for tag in ("<b>v9</b>", "v1.2.3; rm", "../v1", ""):
        assert _latest({"json": _answer(f"{REPO_URL}/releases/tag/x", [], tag=tag)}, monkeypatch) is None


def test_an_oversized_answer_is_not_read_whole(monkeypatch):
    with pytest.raises(httpx.HTTPError):
        _latest({"content": b"[" + b" " * 5_000_000 + b"]"}, monkeypatch)


class _Box:
    """QMessageBox stand-in: records what is shown, presses the first button."""
    Icon, ButtonRole, StandardButton = QMessageBox.Icon, QMessageBox.ButtonRole, QMessageBox.StandardButton
    shown = []

    def __init__(self, *a):
        self.format, self.text, self.info, self.buttons = None, "", "", []
        _Box.shown.append(self)

    def setWindowTitle(self, t): pass
    def setIcon(self, i): pass
    def setTextFormat(self, f): self.format = f
    def setText(self, t): self.text = t
    def setInformativeText(self, t): self.info = t
    def addButton(self, *a):
        b = object()
        self.buttons.append(b)
        return b
    def exec(self): return 0
    def clickedButton(self): return self.buttons[0] if self.buttons else None


@pytest.mark.parametrize("url", HOSTILE)
def test_the_dialog_opens_nothing_outside_the_repository_and_shows_text(monkeypatch, url):
    QApplication.instance() or QApplication([])
    from routemap.gui import app as app_module
    opened = []
    monkeypatch.setattr(app_module, "QMessageBox", _Box)
    monkeypatch.setattr(app_module.QDesktopServices, "openUrl", lambda u: opened.append(u.toString()))
    monkeypatch.setattr(service, "installer_for", lambda assets, **k: ("routemap-0.9.0-macos-arm64.dmg", url))
    controller = app_module.Controller.__new__(app_module.Controller)
    controller.w = None
    _Box.shown.clear()
    controller._update_result({"tag": "v0.9.0", "page": url, "assets": {"x": url},
                               "digests": {"routemap-0.9.0-macos-arm64.dmg": DIGEST}})
    assert all(u.startswith(PREFIX) for u in opened), opened
    assert _Box.shown[-1].format == Qt.PlainText


def test_the_dialog_shows_the_files_sha256_and_how_to_check_it(monkeypatch):
    QApplication.instance() or QApplication([])
    from routemap.gui import app as app_module
    good = f"{REPO_URL}/releases/download/v0.9.0/routemap-0.9.0-macos-arm64.dmg"
    monkeypatch.setattr(app_module, "QMessageBox", _Box)
    monkeypatch.setattr(app_module.QDesktopServices, "openUrl", lambda u: None)
    monkeypatch.setattr(service, "installer_for", lambda assets, **k: ("routemap-0.9.0-macos-arm64.dmg", good))
    controller = app_module.Controller.__new__(app_module.Controller)
    controller.w = None
    _Box.shown.clear()
    controller._update_result({"tag": "v0.9.0", "page": f"{REPO_URL}/releases/tag/v0.9.0",
                               "assets": {"routemap-0.9.0-macos-arm64.dmg": good},
                               "digests": {"routemap-0.9.0-macos-arm64.dmg": DIGEST}})
    info = _Box.shown[-1].info
    assert DIGEST in info and "routemap-0.9.0-macos-arm64.dmg" in info
    assert any(cmd in info for cmd in ("shasum -a 256", "sha256sum", "Get-FileHash"))
