"""An upgrade keeps every setting.

Mac, 26 Oct 2026: the 0.5.0-beta.1 test build started with no origin,
Online lookups off, no history and no city database, though 0.4.0-beta.2
had kept all of them. tests/fixtures/settings/settings-0.4.0-beta.2.json was
written by 0.4.0-beta.2's own Settings class (git show
v0.4.0-beta.2:routemap/config.py) with every field set to something other
than its default. A file that is there and cannot be read is never written
over, and the file an older version left is kept as settings.previous.json."""
import json
import os
import pathlib
import sys

import pytest

from routemap import config

OLD = pathlib.Path(__file__).parent / "fixtures" / "settings" / "settings-0.4.0-beta.2.json"


def _install(text: str) -> pathlib.Path:
    config.config_dir().mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(text, encoding="utf-8")
    return config.settings_path()


def test_every_setting_0_4_0_beta_2_kept_is_read():
    old = json.loads(OLD.read_text())
    _install(OLD.read_text())
    s = config.load_settings()
    assert not isinstance(s, config.SettingsUnreadable)
    for key, value in old.items():
        assert getattr(s, key) == value, key


def test_saving_after_an_upgrade_keeps_the_old_file_and_every_value():
    text = OLD.read_text()
    _install(text)
    s = config.load_settings()
    assert (config.config_dir() / "settings.previous.json").read_text() == text
    config.save_settings(s)
    again = config.load_settings()
    for key, value in json.loads(text).items():
        assert getattr(again, key) == value, key
    assert again.saved_by and json.loads(config.settings_path().read_text())["saved_by"] == again.saved_by
    previous = (config.config_dir() / "settings.previous.json")
    assert previous.read_text() == text          # the same version saving again leaves it alone
    if os.name != "nt":
        assert previous.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("damage", ["garbage", "unreadable"])
def test_a_settings_file_that_cannot_be_read_is_never_written_over(damage):
    if damage == "unreadable" and (os.name == "nt" or os.geteuid() == 0):
        pytest.skip("needs a file this user cannot read")
    path = _install("{not json" if damage == "garbage" else OLD.read_text())
    if damage == "unreadable":
        path.chmod(0)
    s = config.load_settings()
    assert isinstance(s, config.SettingsUnreadable) and str(path) in s.problem
    s.theme = "light"
    if damage == "unreadable":
        path.chmod(0o600)                     # the folder lets the file move; the move must come first
    config.save_settings(s)
    kept = config.config_dir() / "settings.json.unreadable"
    assert kept.read_text() == ("{not json" if damage == "garbage" else OLD.read_text())
    assert config.load_settings().theme == "light"


def test_a_settings_file_that_cannot_be_moved_is_not_replaced(monkeypatch):
    _install("{not json")
    s = config.load_settings()

    def refuse(*a):
        raise PermissionError(1, "Operation not permitted")
    monkeypatch.setattr(config.os, "replace", refuse)
    with pytest.raises(OSError):
        config.save_settings(s)
    assert config.settings_path().read_text() == "{not json"


def test_a_history_that_cannot_be_read_is_kept_not_replaced_by_one_trace():
    config.config_dir().mkdir(parents=True, exist_ok=True)
    config.history_path().write_text("[{broken", encoding="utf-8")
    data = json.loads((pathlib.Path(__file__).parent / "fixtures" / "gui" / "heise_route.json").read_text())
    config.add_history(config.history_entry(data["route"], target="example.org", trace_text=data["trace_text"],
                                            argv=None, source="local"), config.Settings())
    assert (config.config_dir() / "history.json.unreadable").read_text() == "[{broken"
    assert [e["target"] for e in config.load_history()] == ["example.org"]


def test_the_window_says_when_the_settings_were_not_read():
    pytest.importorskip("PySide6")
    from routemap.gui.app import unreadable_text
    _install("{not json")
    text = unreadable_text(config.load_settings())
    assert "settings.json.unreadable" in text and "nothing is written over it" in text


def test_the_tests_never_touch_the_real_config_folder():
    """The isolation is in place from the moment conftest loads, before any
    test module is imported (tests/test_odin_run3_view.py loads its fixture at
    import time and unpacked the ASN database into the real folder)."""
    assert os.environ.get("ROUTEMAP_CONFIG_DIR")
    assert pathlib.Path(os.environ["ROUTEMAP_CONFIG_DIR"]) != config._default_config_dir()
    conftest = sys.modules.get("conftest") or sys.modules.get("tests.conftest")
    assert conftest is not None and conftest.SESSION_CONFIG_DIR
