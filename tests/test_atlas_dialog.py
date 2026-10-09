"""The Atlas trace dialog, offscreen: what each credits state lets the user do."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402
from routemap_engine import atlas  # noqa: E402

from routemap import config, service  # noqa: E402
from routemap.gui import dialogs  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _dialog(state, acknowledged=True, **kw):
    d = dialogs.AtlasTraceDialog(None, target="example.net", acknowledged=acknowledged)
    d.set_credits(service.atlas_credit_view(atlas.Balance(state, **kw), atlas.TRACEROUTE_CREDITS))
    return d


@pytest.mark.parametrize("state,kw,runs,fix", [
    ("ok", {"current": 5000}, True, False),
    ("ok", {"current": 10}, False, False),
    ("bad_key", {"message": "The provided API key does not exist"}, False, True),
    ("no_permission", {}, True, False),
    ("unavailable", {}, True, False),
])
def test_each_state_enables_what_it_should(app, state, kw, runs, fix):
    d = _dialog(state, **kw)
    assert d.go.isEnabled() is runs
    assert d.fix.isVisibleTo(d) is fix


def test_first_trace_needs_the_public_acknowledgement(app):
    d = _dialog("ok", acknowledged=False, current=5000)
    assert d.ack.isVisibleTo(d) and not d.go.isEnabled()
    d.ack.setChecked(True)
    assert d.go.isEnabled()


def test_later_traces_do_not_ask_again(app):
    d = _dialog("ok", acknowledged=True, current=5000)
    assert not d.ack.isVisibleTo(d) and d.go.isEnabled()


def test_open_settings_returns_its_own_code(app):
    d = _dialog("bad_key", message="x")
    d.fix.click()
    assert d.result() == dialogs.AtlasTraceDialog.SETTINGS


def test_the_atlas_tab_index_is_the_atlas_tab(app):
    s = dialogs.SettingsDialog(None, config.Settings())
    assert s.tabs.tabText(dialogs.SettingsDialog.ATLAS_TAB) == "RIPE Atlas"


def test_a_target_is_escaped_in_the_dialog(app):
    d = dialogs.AtlasTraceDialog(None, target="<b>x</b>&")
    from PySide6.QtWidgets import QLabel
    texts = [w.text() for w in d.findChildren(QLabel)]
    assert any("&lt;b&gt;x&lt;/b&gt;&amp;" in t for t in texts)


def test_ripes_reason_is_shown_as_text_never_as_markup(app):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel
    d = _dialog("bad_key", message="<b>bold</b> & it's")
    labels = [w for w in d.credits.findChildren(QLabel) if "bold" in w.text()]
    assert labels and all(w.textFormat() == Qt.PlainText for w in labels)
    assert any("<b>bold</b> & it's" in w.text() for w in labels)
    rows = [w.text() for w in d.credits.findChildren(QLabel)]
    assert not any("&#x27;" in r or "&amp;" in r for r in rows)
