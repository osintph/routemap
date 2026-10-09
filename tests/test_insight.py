"""0.2.0: offline data, the route summary, arcs, comparison and the switches.

No live calls: the DB-IP tests use the bundled ASN file (as a stand-in for any
DB-IP download), and the RIPEstat and Atlas answers are replayed from the
engine's recorded responses through httpx.MockTransport.
"""
import asyncio
import gzip
import json
import pathlib
from importlib import resources

import httpx
import pytest

from routemap import config, dbip, insight, service
from routemap.gui import arcs
from routemap_engine import analyse_sync, baseline, geo, ripe

SAMPLE = resources.files("routemap.gui").joinpath("data/sample_trace.txt").read_text("utf-8")
ORIGIN = (14.5995, 120.9842)
BUNDLED_ASN = resources.files("routemap").joinpath(dbip.BUNDLED_ASN)


@pytest.fixture(autouse=True)
def fresh_reader():
    insight._ASN = None
    service._CITY_READERS.clear()
    yield
    insight._ASN = None


def _sample():
    return analyse_sync(SAMPLE, ORIGIN, sources=geo.OFFLINE).to_dict()


# ------------------------------------------------------------------ arcs ---

def test_great_circle_ends_where_asked_and_takes_small_steps():
    pts = arcs.great_circle(14.6, 121.0, 50.1, 8.7)
    assert pts[0] == (14.6, 121.0)
    assert pts[-1][0] == pytest.approx(50.1, abs=1e-6)
    assert ((pts[-1][1] - 8.7) % 360) == pytest.approx(0, abs=1e-6)
    for (a, b), (c, d) in zip(pts, pts[1:]):
        assert abs(c - a) <= arcs.STEP_DEG + 0.01 and abs(d - b) < 10


@pytest.mark.parametrize("a,b", [((14.6, 121.0), (37.3, -121.9)), ((35.7, 139.7), (-33.9, -70.7)),
                                 ((64.1, -21.9), (61.2, -150.0))])
def test_great_circle_longitudes_never_jump_across_the_antimeridian(a, b):
    pts = arcs.great_circle(*a, *b)
    assert all(abs(d - b_) < 180 for (_, b_), (_, d) in zip(pts, pts[1:]))


def test_segment_steps_measure_from_the_last_rtt_and_skip_silent_groups():
    hop = lambda n, rtt: {"hop": n, "min_rtt_ms": rtt}  # noqa: E731
    groups = [{"hops": [hop(1, 10.0)]}, {"hops": [hop(2, None)]}, {"hops": [hop(3, 90.0)]},
              {"hops": [hop(4, None)], "silent": True}]
    steps = arcs.segment_steps(groups, {"lat": 0, "lon": 0}, quiet_ms=15, hot_ms=60)
    assert [(s["to"], s["class"]) for s in steps] == [(0, "quiet"), (1, "unknown"), (2, "hot")]
    assert steps[2]["step_ms"] == 80.0


# -------------------------------------------------------------- settings ---

def test_settings_are_clamped_on_load(tmp_path):
    path = config.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"projection": "mercator", "rtt_quiet_ms": 50, "rtt_hot_ms": 10,
                                "sensitive_countries": ["sg", "nope", " cn ", 3],
                                "falconeye_url": "javascript:alert(1)"}))
    s = config.load_settings()
    assert s.projection == "flat"
    assert s.rtt_hot_ms > s.rtt_quiet_ms == 50
    assert s.sensitive_countries == ["CN", "SG"]
    assert s.falconeye_url == "https://falconeye.osintph.info"


# --------------------------------------------------------------- DB-IP ---

def test_the_bundled_asn_file_unpacks_once_and_answers():
    db = dbip.asn_database()
    assert db is not None and db.bundled and db.path.exists()
    assert dbip.asn_database().path == db.path
    route = _sample()
    ins = insight.offline(route, config.Settings())
    assert [p["asn"] for p in ins["as_path"]] == [1299, 12306]
    assert all(h.get("asn") is None for h in route["hops"] if h["source"] == "local")


def test_import_accepts_the_right_kind_and_names_the_users_file_otherwise(tmp_path):
    gz = tmp_path / "dbip-asn-lite-2026-10.mmdb.gz"
    gz.write_bytes(BUNDLED_ASN.read_bytes())
    with pytest.raises(dbip.DatabaseError) as err:
        dbip.import_file(gz, "city")
    assert gz.name in str(err.value) and "not DB-IP Lite City" in str(err.value)
    assert dbip.city_database() is None
    junk = tmp_path / "junk.mmdb"
    junk.write_bytes(b"not a database")
    with pytest.raises(dbip.DatabaseError):
        dbip.import_file(junk, "asn")
    db = dbip.import_file(gz, "asn")
    assert db.month and db.path.name == f"dbip-asn-lite-{db.month}.mmdb"


def test_download_falls_back_to_last_month_and_checks_the_file():
    import datetime as dt
    body = BUNDLED_ASN.read_bytes()
    asked = []

    def handler(request):
        asked.append(str(request.url))
        assert request.headers["user-agent"] == "test-agent"
        if "2026-11" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, content=body, headers={"content-length": str(len(body))})

    seen = []
    db = dbip.download("asn", user_agent="test-agent", transport=httpx.MockTransport(handler),
                       today=dt.date(2026, 11, 1), progress=lambda d, t: seen.append((d, t)))
    assert [u.rsplit("/", 1)[-1] for u in asked] == ["dbip-asn-lite-2026-11.mmdb.gz",
                                                     "dbip-asn-lite-2026-10.mmdb.gz"]
    assert db.kind == "asn" and seen[-1] == (len(body), len(body))
    assert not list(dbip.data_dir().glob(".dl-*")), "the temporary download is cleaned up"


def test_a_corrupt_download_never_replaces_the_installed_file():
    good = dbip.asn_database()
    bad = gzip.compress(b"truncated")
    with pytest.raises(dbip.DatabaseError):
        dbip.download("asn", user_agent="x",
                      transport=httpx.MockTransport(lambda r: httpx.Response(200, content=bad)))
    assert dbip.installed("asn").path == good.path


def test_a_cancelled_download_stops_and_leaves_nothing():
    body = BUNDLED_ASN.read_bytes()
    with pytest.raises(dbip.DatabaseError, match="cancelled"):
        dbip.download("city", user_agent="x", cancelled=lambda: True,
                      transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body)))
    assert dbip.city_database() is None
    assert not list(dbip.data_dir().glob(".dl-*"))


# ---------------------------------------------------------- the switches ---

def test_online_lookups_off_turns_every_online_source_off():
    s = config.Settings(online_lookups=False)
    sources = service.sources_for(s)
    assert sources.hoiho is None and sources.ptr is None and sources.ip_db is None
    route = _sample()
    ins = insight.offline(route, s)

    class Boom:
        def __getattr__(self, name):
            raise AssertionError(f"online call {name} with Online lookups off")
    asyncio.run(insight.online(route, ins, s, user_agent="x", sourceapp="x", stat=Boom(), atlas=Boom()))
    assert ins["online"] == {"status": insight.OFF}
    assert asyncio.run(insight.hop_details(route["hops"][6], s, user_agent="x", sourceapp="x",
                                           stat=Boom()))["status"] == insight.OFF


def test_the_offline_city_file_answers_first_and_only_misses_go_online(monkeypatch):
    calls = []

    class City:
        async def __call__(self, addresses):
            return {a: {"lat": 50.1, "lon": 8.7, "city": "Frankfurt", "cc": "DE", "provider": "dbip"}
                    for a in addresses if a.startswith("82.")}

    async def online(addresses, **kw):
        calls.append(list(addresses))
        return {}
    monkeypatch.setattr(service, "offline_city", lambda: City())
    monkeypatch.setattr(geo, "ip_geolocate", online)
    route = analyse_sync(SAMPLE, ORIGIN, sources=service.sources_for(
        config.Settings(use_hoiho=False, use_ptr=False))).to_dict()
    asked = {a for batch in calls for a in batch}
    assert asked and not any(a.startswith("82.") for a in asked)
    assert any(h.get("ip_provider") == "dbip" for h in route["hops"])


# ------------------------------------------------------- online, replayed ---

def _recorded():
    """Real RIPEstat and Atlas answers, recorded once and trimmed (the same files
    as the engine's tests/fixtures/ripe)."""
    root = pathlib.Path(__file__).resolve().parent / "fixtures" / "ripe"
    return json.loads((root / "ripestat.json").read_text()), json.loads((root / "atlas.json").read_text())


def test_the_online_summary_from_recorded_answers():
    stat_rec, atlas_rec = _recorded()

    def stat_handler(request):
        assert request.url.params["sourceapp"] == service.SOURCEAPP
        name = request.url.path.split("/")[2]
        return httpx.Response(200, json=stat_rec["rpki-validation-unknown"]
                              if name == "rpki-validation" and request.url.params["resource"] == "AS12306"
                              else stat_rec[name])

    def atlas_handler(request):
        path = request.url.path
        if path.endswith("/anchors/"):
            return httpx.Response(200, json=atlas_rec[f"anchors-{request.url.params['country']}"])
        if path.endswith("/latest/"):
            return httpx.Response(200, json=atlas_rec["latest"])
        return httpx.Response(200, json=atlas_rec["measurements"])

    route = analyse_sync(SAMPLE, ORIGIN, sources=geo.Sources(ip_db=None)).to_dict()
    # Place the destination at the recorded Frankfurt anchor, so the baseline asks
    # for the measurement that was recorded.
    lat, lon = atlas_rec["expect"]["dest_coords"]
    route["hops"][-1].update(lat=lat, lon=lon, cc="DE", source="ip-db", place="Frankfurt, DE")
    s = config.Settings()
    ins = insight.offline(route, s)
    stat = ripe.RipeStat(user_agent="t", sourceapp=service.SOURCEAPP, transport=httpx.MockTransport(stat_handler))
    atlas = baseline.Baseline(user_agent="t", transport=httpx.MockTransport(atlas_handler))
    asyncio.run(insight.online(route, ins, s, user_agent="t", sourceapp=service.SOURCEAPP,
                               stat=stat, atlas=atlas))
    summary = insight.summary(route, ins, "PH")
    assert ins["online"]["status"] == "done"
    assert summary["as_path"][0]["rpki"]["label"] == "RPKI valid"
    assert summary["ris"]["visibility"].startswith("visible to ")
    assert isinstance(summary["baseline"], dict) and summary["baseline"]["delta"].endswith(" ms")
    assert "RIPE NCC RIPEstat (stat.ripe.net)" in insight.attributions(ins)


def test_a_dead_ripestat_is_unavailable_and_nothing_else():
    route = _sample()
    s = config.Settings()
    ins = insight.offline(route, s)
    path_before = list(ins["as_path"])
    dead = httpx.MockTransport(lambda r: httpx.Response(503))
    stat = ripe.RipeStat(user_agent="t", sourceapp="t", transport=dead)
    atlas = baseline.Baseline(user_agent="t", transport=dead)
    asyncio.run(insight.online(route, ins, s, user_agent="t", sourceapp="t", stat=stat, atlas=atlas))
    assert ins["as_path"] == path_before
    assert all(v["rpki"] == insight.UNAVAILABLE for v in ins["online"]["hops"].values())
    assert insight.summary(route, ins)["as_path"][0]["rpki"] is None


# ------------------------------------------------------------- exports ---

def test_the_json_export_carries_the_summary_and_comparison_and_stays_schema_valid():
    jsonschema = pytest.importorskip("jsonschema")
    from routemap_engine import diff, schema
    route = _sample()
    ins = insight.offline(route, config.Settings())
    old = _sample()
    d = diff.diff_routes(old, route)
    doc = json.loads(service.export_json(route, target="heise.de", trace_text=SAMPLE, argv=None,
                                         source="file", origin_how="coords", insight=ins,
                                         comparison={"label": "x", "summary": d["summary"]}))
    assert doc["format_version"] == 3 and doc["insight"]["as_path"]
    assert any("DB-IP" in a for a in doc["attributions"])
    assert "routemap-engine" in doc["schema"]
    jsonschema.validate(doc["route"], schema())
