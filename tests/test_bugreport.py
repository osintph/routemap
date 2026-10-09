"""The bug report: what the dialog shows is what the zip holds, and no secret is in either.

Generalised over the class of leak: a random secret planted in every
secret-named setting, in a nested setting and as a UUID-shaped value in an
innocent field never appears in any file, with or without the last trace; the
origin appears only when the user includes the trace.
"""
import dataclasses
import json
import uuid
import zipfile

import pytest

from routemap import bugreport, config


def _settings(**kw):
    s = config.Settings()
    s.atlas_key = str(uuid.uuid4())
    s.origin_mode = config.ORIGIN_CITY
    s.origin_lat, s.origin_lon, s.origin_label = 14.5995, 120.9842, "Manila, PH"
    for k, v in kw.items():
        setattr(s, k, v)
    return s


CURRENT = {"target": "example.net", "trace_text": "traceroute to example.net\n", "argv": ["icmp"],
           "route": {"origin": {"lat": 14.5995, "lon": 120.9842, "label": "Manila, PH"}, "hops": []}}


def _all_bytes(files):
    return b"".join(data for _, data in files)


@pytest.mark.parametrize("include", [False, True])
def test_no_key_reaches_the_report(include):
    s = _settings()
    planted = str(uuid.uuid4())
    s.window_geometry = f"geometry {planted}"           # a UUID in an innocent field
    s.flags = {"icmp": ["-x"], "api_token": [planted]}  # a secret name, nested
    blob = _all_bytes(bugreport.contents(s, CURRENT, include))
    assert s.atlas_key.encode() not in blob and planted.encode() not in blob
    assert bugreport.REMOVED.encode() in blob


def test_every_secret_named_field_is_removed():
    for name in ("atlas_key", "api_key", "token", "SECRET", "password", "passphrase", "auth_header"):
        data = bugreport._scrub({name: "value-that-must-go"})
        assert data[name] == bugreport.REMOVED, name


def test_an_empty_key_stays_visibly_empty():
    view = bugreport.settings_view(_settings(atlas_key=""), include_origin=False)
    assert view["atlas_key"] == ""


def test_the_origin_is_left_out_unless_the_trace_is_included():
    s = _settings()
    without = json.loads(dict(bugreport.contents(s, CURRENT, False))[bugreport.SETTINGS])
    assert all(without[f] == bugreport.REMOVED for f in bugreport.ORIGIN_FIELDS)
    assert b"120.98" not in _all_bytes(bugreport.contents(s, CURRENT, False))
    with_trace = json.loads(dict(bugreport.contents(s, CURRENT, True))[bugreport.SETTINGS])
    assert with_trace["origin_lat"] == 14.5995


def test_ticking_the_trace_with_nothing_on_screen_adds_nothing():
    names = [n for n, _ in bugreport.contents(_settings(), None, True)]
    assert names == [bugreport.ABOUT, bugreport.SETTINGS]
    view = json.loads(dict(bugreport.contents(_settings(), None, True))[bugreport.SETTINGS])
    assert view["origin_lat"] == bugreport.REMOVED


def test_the_trace_only_when_ticked():
    assert bugreport.TRACE not in dict(bugreport.contents(_settings(), CURRENT, False))
    assert bugreport.TRACE in dict(bugreport.contents(_settings(), CURRENT, True))


def test_a_private_falconeye_address_is_removed():
    view = bugreport.settings_view(_settings(falconeye_url="https://fe.internal.example"), False)
    assert view["falconeye_url"] == bugreport.REMOVED
    assert bugreport.settings_view(_settings(), False)["falconeye_url"] == bugreport.DEFAULT_FALCONEYE


def test_the_zip_holds_exactly_what_was_shown(tmp_path):
    files = bugreport.contents(_settings(), CURRENT, True)
    path = tmp_path / "r.zip"
    bugreport.write_zip(path, files)
    with zipfile.ZipFile(path) as z:
        assert [(i.filename, z.read(i)) for i in z.infolist()] == files


def test_every_setting_is_accounted_for():
    """A setting added later appears in the report (scrubbed), never silently dropped."""
    names = {f.name for f in dataclasses.fields(config.Settings)}
    assert set(bugreport.settings_view(_settings(), False)) == names


def test_about_names_version_engine_and_os():
    text = bugreport.about_text()
    assert "routemap-engine" in text and "OS " in text and "Qt " in text
