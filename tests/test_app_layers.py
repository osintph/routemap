"""Settings, history, exports, the CLI and the Atlas result format.

Everything here runs with ROUTEMAP_CONFIG_DIR pointed at a temporary folder and
every network source off, so it touches nothing outside the test.
"""
import json
import os
import pathlib

import jsonschema
import pytest

from routemap import cli, config, service
from routemap_engine import OFFLINE, analyse_sync, atlas, parse_trace, schema

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "routemap"


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTEMAP_CONFIG_DIR", str(tmp_path / "cfg"))
    return tmp_path / "cfg"


def test_settings_default_round_trip_and_survive_junk(isolated_config):
    s = config.load_settings()
    assert s.origin() is None and s.history_enabled and s.flags["traceroute"][:2] == ["-m", "30"]
    s.origin_mode, s.origin_lat, s.origin_lon, s.origin_label = "city", 1.29, 103.85, "Singapore, SG"
    s.flags["traceroute"] = ["-m", "20"]
    config.save_settings(s)
    again = config.load_settings()
    assert again.origin() == (1.29, 103.85, "Singapore, SG")
    assert again.flags["traceroute"] == ["-m", "20"] and again.flags["tracert"][0] == "-h"
    config.settings_path().write_text("{not json")
    assert config.load_settings().origin() is None


def test_history_is_capped_newest_first_and_off_means_nothing_stored(isolated_config):
    s = config.load_settings()
    route = {"hops": [{"lat": 1.0}, {"lat": None}]}
    for i in range(config.HISTORY_LIMIT + 5):
        config.add_history(config.history_entry(route, target=f"t{i}", trace_text="x",
                                                argv=None, source="paste"), s)
    entries = config.load_history()
    assert len(entries) == config.HISTORY_LIMIT and entries[0]["target"] == f"t{config.HISTORY_LIMIT + 4}"
    assert entries[0]["placed"] == 1
    assert config.clear_history() == config.HISTORY_LIMIT
    s.history_enabled = False
    config.add_history(config.history_entry(route, target="x", trace_text="", argv=None,
                                            source="paste"), s)
    assert not config.history_path().exists()


def test_the_json_export_wraps_a_schema_valid_route():
    text = (FIXTURES / "heise_traceroute.txt").read_text()
    route = analyse_sync(text, (14.6, 121.0), sources=OFFLINE)
    doc = json.loads(service.export_json(route, target="heise.de", trace_text=text,
                                         argv=["/usr/sbin/traceroute", "-m", "30", "heise.de"],
                                         source="local", origin_how="ip"))
    assert doc["format"] == service.EXPORT_FORMAT and doc["trace"]["argv"][0] == "traceroute"
    jsonschema.validate(doc["route"], schema())


@pytest.mark.parametrize("text,label", [("Manila, PH", "Manila"), ("14.6, 121.0", "Manila"),
                                        ("san jose, us", "San Jose")])
def test_an_origin_can_be_typed_as_a_city_or_coordinates(text, label):
    lat, lon, display = service.parse_origin_text(text)
    assert display.startswith(label)


def test_an_unknown_origin_is_an_error():
    with pytest.raises(ValueError):
        service.parse_origin_text("Atlantis of the Deep")


def test_cli_parse_writes_png_pdf_and_json(tmp_path, capsys):
    pytest.importorskip("PySide6")
    png, pdf = tmp_path / "m.png", tmp_path / "r.pdf"
    code = cli.main(["parse", str(FIXTURES / "amazon_mtr.txt"), "--origin", "Manila, PH",
                     "--offline", "--json", "--png", str(png), "--pdf", str(pdf)])
    assert code == 0
    body = json.loads(capsys.readouterr().out)
    assert len(body["hops"]) == 18
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert pdf.read_bytes()[:5] == b"%PDF-"


def test_the_pdf_report_carries_the_sections_it_promises(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtPdf import QPdfDocument

    from routemap.gui.app import make_app, write_export
    make_app()
    text = (FIXTURES / "amazon_mtr.txt").read_text()
    route = analyse_sync(text, (14.6, 121.0), sources=OFFLINE).to_dict()
    path = tmp_path / "r.pdf"
    write_export("pdf", str(path), {"route": route, "target": "amazon.com", "trace_text": text,
                                    "argv": ["mtr", "--report-wide", "amazon.com"],
                                    "source": "local", "origin_how": "ip"})
    doc = QPdfDocument()
    doc.load(str(path))
    words = " ".join(doc.getAllText(i).text() for i in range(doc.pageCount()))
    for needle in ("Route to amazon.com", "Hops", "Unplaced hops", "How locations were decided",
                   "Appendix: raw trace", "approximate, wrong on a VPN"):
        assert needle in words, needle
    assert chr(0x2014) not in words


def test_the_smoke_test_passes_from_source(tmp_path, capsys):
    pytest.importorskip("PySide6")
    assert cli.main(["--smoke-test", str(tmp_path)]) == 0
    assert "smoke test ok" in capsys.readouterr().out


def test_an_atlas_result_renders_as_traceroute_text_the_parser_reads():
    result = {"dst_name": "heise.de", "dst_addr": "193.99.144.80", "result": [
        {"hop": 1, "result": [{"from": "192.168.1.1", "rtt": 1.2}, {"from": "192.168.1.1", "rtt": 1.0},
                              {"x": "*"}]},
        {"hop": 2, "result": [{"x": "*"}, {"x": "*"}, {"x": "*"}]},
        {"hop": 3, "result": [{"from": "62.115.112.222", "rtt": 58.3,
                               "name": "sng-b6-link.ip.twelve99.net"}]},
    ]}
    parsed = parse_trace(atlas.to_trace_text(result))
    assert parsed.parser == "traceroute" and parsed.target == "193.99.144.80"
    assert [h.hop for h in parsed.hops] == [1, 2, 3]
    assert parsed.hops[0].lost == 1 and parsed.hops[1].lost == 3
    assert parsed.hops[2].hostnames == ["sng-b6-link.ip.twelve99.net"]


def test_atlas_without_a_key_says_where_to_add_one():
    with pytest.raises(atlas.AtlasUnavailable) as excinfo:
        atlas.Atlas("  ")
    assert excinfo.value.kind == "auth" and "Settings" in excinfo.value.message


def test_atlas_never_sends_the_origin():
    """Probe selection may rank by distance here; it must never filter by radius."""
    source = pathlib.Path(atlas.__file__).read_text(encoding="utf-8")
    assert "radius" not in source.split('"""', 2)[2]


def test_turning_ripestat_off_removes_every_ripestat_call(monkeypatch):
    """The RIPEstat switch: no IP database, no public-IP origin lookup."""
    import asyncio

    from routemap import policy
    monkeypatch.setattr(policy, "RIPESTAT_ALLOWED", False)
    sources = service.sources_for(config.load_settings())
    assert sources.ip_db is None and sources.hoiho is not None and sources.ptr is not None
    with pytest.raises(RuntimeError) as excinfo:
        asyncio.run(service.resolve_origin(config.load_settings()))
    assert "Settings" in str(excinfo.value)


def test_turning_hoiho_off_leaves_site_codes_and_ptr():
    from routemap import policy
    original = policy.HOIHO_ALLOWED
    try:
        policy.HOIHO_ALLOWED = False
        sources = service.sources_for(config.load_settings())
        assert sources.hoiho is None and sources.ptr is not None
    finally:
        policy.HOIHO_ALLOWED = original


def test_ip_database_answers_are_cached_and_sent_with_sourceapp(monkeypatch):
    """Each address is asked once per cache lifetime, identified as this app."""
    import asyncio

    from routemap_engine import geo
    calls = []

    async def fake(addresses, *, user_agent, sourceapp, timeout=10.0):
        calls.append((list(addresses), sourceapp))
        return {a: {"lat": 1.29, "lon": 103.85, "city": "Singapore", "cc": "SG"}
                for a in addresses if a != "62.115.9.9"}

    monkeypatch.setattr(geo, "ip_geolocate", fake)
    ip_db = service.sources_for(config.load_settings()).ip_db
    first = asyncio.run(ip_db(["62.115.1.1", "62.115.9.9"]))
    second = asyncio.run(ip_db(["62.115.1.1", "62.115.9.9"]))
    assert first == second and "62.115.9.9" not in first
    assert calls == [(["62.115.1.1", "62.115.9.9"], "routemap-desktop"),
                     (["62.115.9.9"], "routemap-desktop")], "a cached answer was asked again, or a miss was cached"
