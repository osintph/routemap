"""
Static mockup: the real window and dialogs, fed fixture data, one state at a time.

    python -m routemap.gui.mockup --out screenshots/          # every state, PNGs
    python -m routemap.gui.mockup --show result               # one state, interactive

Run from a checkout: the data comes from tests/fixtures/gui/, which are real
engine analyses of recorded traces (one derived to show an ECMP hop; its file
says so). Nothing here traces or contacts anything.

Works headless with QT_QPA_PLATFORM=offscreen, which is how CI renders the
Linux and Windows screenshots when no desktop session is available.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from routemap.__about__ import DISPLAY_NAME, VERSION
from routemap_engine import runner
from routemap.gui import dialogs, geometry, mapview, theme
from routemap.gui.mainwindow import MainWindow

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "gui"
MANILA = (14.6, 121.0, "Manila, NCR, PH")
WINDOW = QSize(1440, 900)


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _platform_tool() -> str:
    return "tracert" if sys.platform.startswith("win") else "traceroute"


def _argv(target: str) -> list[str]:
    tool = _platform_tool()
    return runner.build_argv(tool, tool, target)


HISTORY = [
    {"target": "heise.de", "when": "3 Oct 13:05", "hops": 16, "placed": 16,
     "tool": "traceroute -m 30 -q 3 -w 1"},
    {"target": "amazon.com", "when": "3 Oct 12:41", "hops": 18, "placed": 12,
     "tool": "mtr --report-wide --show-ips -c 3 -m 30"},
    {"target": "1.1.1.1", "when": "2 Oct 21:17", "hops": 7, "placed": 7,
     "tool": "traceroute -m 30 -q 3 -w 1"},
    {"target": "bbc.co.uk", "when": "2 Oct 20:58", "hops": 14, "placed": 11,
     "tool": "traceroute -m 30 -q 3 -w 1"},
]


def set_scheme(dark: bool):
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    QApplication.processEvents()


def _settle(widget: QWidget, rounds: int = 6):
    for _ in range(rounds):
        QApplication.processEvents()
    widget.repaint()
    QApplication.processEvents()


def _window() -> MainWindow:
    window = MainWindow()
    window.resize(WINDOW)
    window.set_origin_status(MANILA[2], "ip")
    window.set_tool_status(_argv("example.com"))
    window.history.set_entries(HISTORY)
    return window


# ------------------------------------------------------------------ states ---

def state_idle(window: MainWindow):
    window.show_idle(MANILA)


def state_no_tool(window: MainWindow):
    window.set_tool_status(None, missing_hint=runner.install_hint())
    hint = (f"Install one, then restart {DISPLAY_NAME}:<br><br>"
            "<code>sudo apt install traceroute</code> &nbsp;Debian, Ubuntu<br>"
            "<code>sudo dnf install traceroute</code> &nbsp;Fedora<br>"
            "<code>sudo pacman -S traceroute</code> &nbsp;Arch<br><br>"
            "mtr is optional and adds per-hop loss: <code>sudo apt install mtr-tiny</code>."
            "<br><br>You can still analyse traces run elsewhere: <b>File › Paste Trace</b>.")
    window.show_idle(MANILA, tool_hint=hint)


def state_tracing(window: MainWindow):
    """Mid-trace: nine hops in, placed as they arrived; the output panel open."""
    source = "heise_tracert.txt" if _platform_tool() == "tracert" else "heise_traceroute.txt"
    text = (ROOT / "tests" / "fixtures" / "routemap" / source).read_text().splitlines()
    shown = [line for line in text if line.strip()][:10]
    window.show_tracing("heise.de", _argv("heise.de"), shown, "hop 9")
    route = _fixture("heise_ecmp_route")["route"]
    partial = dict(route, hops=[dict(h, annotations=[]) for h in route["hops"][:9]])
    window.update_live(partial, "heise.de", "hop 9")
    window.live.toggle.setChecked(True)


def state_result(window: MainWindow):
    data = _fixture("heise_ecmp_route")
    window.show_result(data["route"], "heise.de", _argv("heise.de"), trace_text=data["trace_text"])
    window.history_dock.show()
    window.table.select_hops([10, 11])
    window.map.highlight([10, 11])


def state_unplaced(window: MainWindow):
    data = _fixture("amazon_route")
    window.show_result(data["route"], "amazon.com", _argv("amazon.com"), expand_unplaced=True,
                       trace_text=data["trace_text"])


STATES = {
    "idle": state_idle,
    "no-tool": state_no_tool,
    "tracing": state_tracing,
    "result": state_result,
    "unplaced": state_unplaced,
}


def _tooltip_card(route: dict, hop_number: int) -> QLabel:
    """A marker's hover tooltip, drawn as Qt draws tooltips, for a screenshot."""
    group = next(g for g in mapview.route_groups(route)
                 if any(h["hop"] == hop_number for h in g["hops"]))
    label = QLabel(mapview.group_tooltip(group, route["origin"]["label"]))
    label.setTextFormat(Qt.RichText)
    label.setWindowFlags(Qt.ToolTip)
    label.setMargin(8)
    label.setForegroundRole(QPalette.ToolTipText)
    label.setBackgroundRole(QPalette.ToolTipBase)
    label.setAutoFillBackground(True)
    return label


def render_all(out: pathlib.Path) -> list[pathlib.Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []

    def save(widget: QWidget, name: str):
        _settle(widget)
        path = out / f"{name}.png"
        widget.grab().save(str(path))
        written.append(path)

    for dark in (False, True):
        set_scheme(dark)
        suffix = "-dark" if dark else ""
        for name, build in STATES.items():
            if dark and name not in ("idle", "tracing", "result", "unplaced"):
                continue
            window = _window()
            window.show()
            build(window)
            _settle(window)
            if name in ("result", "unplaced"):
                window.map.fit_route()
            save(window, f"{len(written) + 1:02d}-{name}{suffix}")
            window.close()

    set_scheme(False)
    route = _fixture("heise_ecmp_route")["route"]
    card = _tooltip_card(route, 8)
    card.show()
    save(card, f"{len(written) + 1:02d}-ecmp-tooltip")
    card.close()

    window = _window()
    window.show()
    state_result(window)
    _settle(window)
    for name, dialog in (
        ("export", dialogs.ExportDialog(window, selected="pdf")),
        ("atlas-warning", dialogs.AtlasTraceDialog(window, target="heise.de")),
        ("paste", dialogs.PasteTraceDialog(
            window, text=_fixture("amazon_route")["trace_text"],
            detected="Detected: mtr --report, 18 hops", origin_label=MANILA[2])),
        ("privacy", dialogs.PrivacyDialog(window)),
    ):
        dialog.show()
        save(dialog, f"{len(written) + 1:02d}-{name}")
        dialog.close()

    settings = dialogs.SettingsDialog(window, origin_label=MANILA[2],
                                      tools=runner.available_tools() or {"traceroute": "x"},
                                      cache_count=214, history_count=4)
    settings.show()
    for index in range(settings.tabs.count()):
        settings.tabs.setCurrentIndex(index)
        tab = settings.tabs.tabText(index).lower().replace(" ", "-")
        save(settings, f"{len(written) + 1:02d}-settings-{tab}")
    settings.close()
    window.close()

    image = mapview.render_png(route, title="heise.de from Manila",
                               provenance=f"{DISPLAY_NAME} {VERSION} · 3 Oct 2026 13:05 · "
                                          "traceroute -m 30 -q 3 -w 1 · "
                                          f"{geometry.ATTRIBUTION} · GeoNames CC BY 4.0",
                               destination="heise.de")
    path = out / f"{len(written) + 1:02d}-export-png-1600x900.png"
    image.save(str(path))
    written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the GUI mockup.")
    parser.add_argument("--out", type=pathlib.Path, help="write every state as PNG here")
    parser.add_argument("--show", choices=sorted(STATES), help="open one state interactively")
    parser.add_argument("--dark", action="store_true")
    args = parser.parse_args(argv)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(DISPLAY_NAME)
    if args.out:
        for path in render_all(args.out):
            print(path)
        return 0
    set_scheme(args.dark)
    window = _window()
    window.show()
    STATES[args.show or "result"](window)
    QTimer.singleShot(0, window.map.fit_route)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
