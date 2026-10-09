"""The update dialog, offscreen: each state offers only what it should."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from routemap.gui import dialogs  # noqa: E402

NAME = "routemap-0.2.0-beta.6-linux-x86_64.AppImage"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _d():
    return dialogs.UpdateDialog(None, tag="v0.2.0-beta.6", current="v0.2.0-beta.5", name=NAME)


def _visible(d):
    return {n for n in ("go", "notes", "close_button", "cancel_button", "hand", "page")
            if getattr(d, n).isVisibleTo(d)}


def test_offer(app):
    d = _d()
    assert _visible(d) == {"go", "notes", "close_button"}
    assert NAME in d.body.text()


def test_checking_offers_only_cancel(app):
    d = _d()
    d.checking()
    assert _visible(d) == {"cancel_button"}


def test_verified_offers_the_hand_over(app):
    d = _d()
    d.checking()
    for s in ("download", "signature", "hash"):
        d.step(s, "ok")
    d.verified("Verified. Route Map replaces this AppImage with the new one and restarts.",
               "Restart with the update")
    assert _visible(d) == {"hand", "close_button"}
    assert d.hand.text() == "Restart with the update"
    assert all(m.text() == dialogs.UpdateDialog.MARKS["ok"] for m in d.rows.values())
    assert all(m.accessibleName().endswith("passed") for m in d.rows.values())


@pytest.mark.parametrize("step", ["download", "signature", "hash"])
def test_a_failed_check_never_offers_to_install(app, step):
    d = _d()
    d.checking()
    d.failed(step, "The signature on SHA256SUMS is not by the Route Map update key for v0.2.0-beta.6.")
    assert "hand" not in _visible(d) and {"page", "close_button"} <= _visible(d)
    assert d.rows[step].text() == dialogs.UpdateDialog.MARKS["failed"]
    assert "deleted" in d.result_text.text() and "nothing was installed" in d.result_text.text()


def test_a_hostile_message_is_escaped(app):
    d = _d()
    d.failed("download", "<img src=x>")
    assert "<img" not in d.result_text.text()
