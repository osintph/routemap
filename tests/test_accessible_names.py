"""Every control a person can operate has a name a screen reader can read.

Walks every widget of the main window, with a result on screen, and of every
dialog, so a control added later without a name fails here rather than in a
screen reader. A control counts as named when it has an accessible name, a
button with text, or a label whose buddy it is (QFormLayout rows set that).
"""
import json
import pathlib

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QAbstractSlider, QAbstractSpinBox,  # noqa: E402
                               QApplication, QComboBox, QGraphicsView, QLabel, QLineEdit, QPlainTextEdit,
                               QTabBar, QTextEdit, QWidget)

from routemap import config  # noqa: E402
from routemap.gui import dialogs  # noqa: E402

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "gui"
OPERABLE = (QAbstractButton, QLineEdit, QComboBox, QAbstractSpinBox, QAbstractItemView, QPlainTextEdit,
            QTextEdit, QAbstractSlider, QGraphicsView, QTabBar)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def part_of_a_control(w: QWidget) -> bool:
    """Scroll bars, header sections, a line edit's clear button, a spin box's or
    combo box's own editor: read by the screen reader with their control."""
    from PySide6.QtWidgets import QHeaderView, QScrollBar, QToolButton
    parent = w.parent()
    return (isinstance(w, (QScrollBar, QHeaderView, QTabBar))
            or (isinstance(w, QToolButton) and isinstance(parent, QLineEdit))
            or (isinstance(w, QLineEdit) and isinstance(parent, (QComboBox, QAbstractSpinBox))))


def unnamed(root: QWidget) -> list[str]:
    buddies = {id(l.buddy()) for l in root.findChildren(QLabel) if l.buddy() is not None}
    out = []
    for w in [root, *root.findChildren(QWidget)]:
        if not isinstance(w, OPERABLE) and not w.focusPolicy() & 0x8:   # Qt.StrongFocus has the wheel bit
            continue
        if not isinstance(w, OPERABLE) and type(w).__module__.startswith("PySide6"):
            continue
        if w.accessibleName().strip() or id(w) in buddies:
            continue
        if isinstance(w, QAbstractButton) and w.text().replace("&", "").strip():
            continue
        if part_of_a_control(w):
            continue   # parts of a named control, read with it
        if not w.isVisibleTo(root) and w is not root:
            continue
        out.append(f"{type(w).__name__} {w.objectName() or ''} in {type(w.parent()).__name__ if w.parent() else '-'}")
    return out


def _main_window():
    from routemap.gui.mainwindow import MainWindow
    w = MainWindow()
    w.resize(1440, 900)
    route = json.loads((FIX / "heise_route.json").read_text())["route"]
    w.show_result(route, "heise.de", ["icmp", "heise.de"])
    w.table.set_hops(route["hops"], {})
    return w


def _dialogs():
    s = config.Settings()
    yield "settings", dialogs.SettingsDialog(None, s)
    yield "export", dialogs.ExportDialog(None, selected="pdf")
    yield "atlas", dialogs.AtlasTraceDialog(None, target="example.net")
    yield "update", dialogs.UpdateDialog(None, tag="v1", current="v0", name="x.AppImage")
    yield "bug", dialogs.BugReportDialog(None, build=lambda inc: [("a.txt", b"x")], has_trace=False)
    yield "paste", dialogs.PasteTraceDialog(None, text="", detected="", origin_label="")
    yield "privacy", dialogs.PrivacyDialog(None)
    yield "notices", dialogs.NoticesDialog(None)
    yield "support", dialogs.SupportDialog(None)
    yield "city", dialogs.CityDatabaseDialog(None)
    yield "download", dialogs.DownloadDialog(None)


def test_the_main_window_names_every_control(app):
    w = _main_window()
    w.show()
    app.processEvents()
    missing = unnamed(w)
    w.close()
    assert not missing, "\n".join(missing)


DIALOGS = ["settings", "export", "atlas", "update", "bug", "paste", "privacy", "notices", "support", "city",
           "download"]


@pytest.mark.parametrize("name", DIALOGS)
def test_every_dialog_names_every_control(app, name):
    d = dict(_dialogs())[name]
    d.show()
    app.processEvents()
    missing = unnamed(d)
    d.close()
    assert not missing, "\n".join(missing)
