"""The window's part of the VPN and SASE work (0.5.0-beta.5): the notice bar, the
details panel, the interface list and its refresh, the export box, the one-time
notice and the help view. Adapters are mocked; nothing is sent."""
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from routemap import config, netnotes
from routemap.__about__ import DISPLAY_NAME
from routemap_engine import interfaces as I


def adapter(name, kind, up=True):
    return I.Adapter("id-" + name, name, "A driver", kind, up, 7, 7, False, ["192.0.2.10"], [], [])


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    from routemap.gui.mainwindow import MainWindow
    w = MainWindow()
    yield w
    w.close()


def test_the_notice_bar_shows_and_clears(window):
    window.set_notice(netnotes.notice_html({"kind": "tunnel", "label": "t0"}, None))
    assert not window.notice.isHidden() and "goes through t0" in window.notice.text()
    window.show_tracing("example.net", ["icmp"])
    assert window.notice.isHidden()


def test_an_unclassified_adapter_gets_no_notice_but_is_in_the_details(window):
    block = {"kind": "unclassified", "label": "vSwitch"}
    window.set_notice(netnotes.notice_html(block, None, origin_auto=True))
    window.insight.set_interface(netnotes.details_text(block))
    assert window.notice.isHidden()
    head, content = window.insight.sections["interface"]
    assert not content.isHidden() and "vSwitch (unclassified)" in content.text()
    window.insight.set_interface(None)
    assert content.isHidden()


def test_the_details_panel_escapes_the_name(window):
    window.insight.set_interface("<b>x</b> (tunnel)")
    assert "&lt;b&gt;" in window.insight.sections["interface"][1].text()


def test_down_adapters_are_listed_and_cannot_be_picked(app, monkeypatch):
    from routemap.gui.dialogs import InterfaceCombo
    monkeypatch.setattr(I, "list_adapters", lambda: [adapter("eth0", "physical"), adapter("off0", "physical", up=False)])
    combo = InterfaceCombo("", "")
    assert combo.currentData() == "" and combo.itemText(0) == "Automatic (system route)"
    assert combo.model().item(1).isEnabled() and "eth0 (A driver), physical, up, 192.0.2.10" == combo.itemText(1)
    assert not combo.model().item(2).isEnabled() and "down" in combo.itemText(2)


def test_the_list_is_read_again_when_opened(app, monkeypatch):
    from routemap.gui.dialogs import InterfaceCombo
    listed = [adapter("eth0", "physical")]
    monkeypatch.setattr(I, "list_adapters", lambda: list(listed))
    combo = InterfaceCombo("id-eth0", "eth0")
    assert combo.count() == 2 and combo.currentData() == "id-eth0"
    listed.append(adapter("t0", "tunnel"))
    combo.showPopup()
    combo.hidePopup()
    assert combo.count() == 3 and combo.currentData() == "id-eth0" and combo.chosen_name() == "eth0"


def test_a_saved_adapter_that_is_gone_is_shown_and_kept(app, monkeypatch):
    from routemap.gui.dialogs import InterfaceCombo
    monkeypatch.setattr(I, "list_adapters", lambda: [])
    combo = InterfaceCombo("id-gone", "Old adapter")
    assert combo.currentData() == "id-gone" and "Old adapter (not on this computer now)" in combo.currentText()
    assert combo.chosen_name() == "Old adapter"


def test_the_list_survives_the_os_call_failing(app, monkeypatch):
    from routemap.gui.dialogs import InterfaceCombo
    def boom():
        raise OSError("no")
    monkeypatch.setattr(I, "list_adapters", boom)
    assert InterfaceCombo("", "").count() == 1


def test_the_export_box_is_off_by_default(app):
    from routemap.gui.dialogs import ExportDialog
    assert ExportDialog().interface_addresses.isChecked() is False


def test_the_help_view_renders_the_bundled_text_plainly(app):
    from PySide6.QtWidgets import QTextBrowser
    from routemap.gui.dialogs import HelpDialog
    dialog = HelpDialog()
    view = dialog.findChild(QTextBrowser)
    assert f"Using {DISPLAY_NAME} behind a VPN or SASE client" in view.toPlainText()
    assert "{NAME}" not in view.toPlainText() and view.styleSheet() == ""


def test_the_help_is_in_the_help_menu(window):
    assert window.act_vpn_help.text() == f"Using {DISPLAY_NAME} behind a VPN or SASE client"


def test_the_privacy_text_says_adapters_stay_local():
    from routemap.gui.dialogs import PRIVACY_HTML
    assert "read locally" in PRIVACY_HTML and "never sent anywhere" in PRIVACY_HTML and "tick" in PRIVACY_HTML


def _controller(window, settings):
    from routemap.gui.app import Controller
    c = Controller.__new__(Controller)
    c.w, c.settings, c.current = window, settings, None
    return c


def test_the_bypass_notice_shows_once(window, monkeypatch):
    seen = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a: seen.append(a[2]))
    monkeypatch.setattr(I, "list_adapters", lambda: [adapter("eth0", "physical"), adapter("t0", "tunnel")])
    settings = config.Settings(probe_interface="id-eth0")
    c = _controller(window, settings)
    c._bypass_notice("")
    c._bypass_notice("")
    assert len(seen) == 1 and "may bypass" in seen[0] and config.load_settings().bypass_notice_seen


def test_refresh_notices_warns_about_the_origin_only_for_a_new_run(window):
    c = _controller(window, config.Settings())
    c.current = {"route": {"hops": []}, "interface": {"kind": "tunnel", "label": "t0"}}
    c._refresh_notices(fresh=True)
    assert "Origin is on Auto" in window.notice.text()
    c._refresh_notices(fresh=False)
    assert "Origin is on Auto" not in window.notice.text() and "This trace went through t0" in window.notice.text()
