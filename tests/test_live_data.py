"""Continuous mode's data: merging, placing only what is new, the history cap,
settings bounds, and a session from a file rebuilt like everything else."""
import json
import math

import pytest
from routemap_engine import geo

from routemap import config, imported, live


def _snap_hops():
    hops = [{"hop": n, "addresses": [f"192.0.2.{n}"], "sent": 100, "received": 100 if n != 3 else 60,
             "loss_pct": 0.0 if n != 3 else 40.0, "last_ms": 5.0 * n, "best_ms": 4.0 * n, "avg_ms": 5.0 * n,
             "worst_ms": 9.0 * n, "stdev_ms": 0.5, "annotations": [], "min_rtt_ms": 4.0 * n} for n in range(1, 6)]
    geo.annotate(hops)
    return hops


def _route_hops():
    return [{"hop": n, "addresses": [f"192.0.2.{n}"], "address": f"192.0.2.{n}", "lat": 10.0 + n, "lon": 20.0,
             "place": f"Town {n}", "source": "ip-db", "annotations": [], "loss_pct": None,
             "min_rtt_ms": 1.0} for n in (1, 2, 3, 4)]


def test_merge_keeps_placements_and_takes_the_sessions_figures():
    merged = live.merge_hops(_route_hops(), _snap_hops())
    assert [h["hop"] for h in merged] == [1, 2, 3, 4, 5]
    assert merged[0]["place"] == "Town 1" and merged[0]["lat"] == 11.0
    assert merged[0]["min_rtt_ms"] == 4.0 and merged[0]["avg_rtt_ms"] == 5.0
    assert merged[4]["lat"] is None and merged[4]["source"] == "unresolved"     # not placed yet
    assert geo.ANNOT_ICMP_LIMIT in merged[2]["annotations"]
    assert all(geo.ANNOT_ICMP_LIMIT not in h["annotations"] for h in merged if h["hop"] != 3)


def test_a_stale_rate_limit_note_from_the_route_is_replaced():
    route = _route_hops()
    route[0]["annotations"] = [geo.ANNOT_ICMP_LIMIT]
    merged = live.merge_hops(route, _snap_hops())
    assert geo.ANNOT_ICMP_LIMIT not in merged[0]["annotations"]


def test_only_hops_and_addresses_not_placed_are_placed_again():
    snap = _snap_hops()
    snap[1]["addresses"].append("198.51.100.7")        # ECMP sibling at hop 2
    todo = live.unplaced(snap, _route_hops())
    assert [(h.hop, h.addresses) for h in todo] == [(2, ["198.51.100.7"]), (5, ["192.0.2.5"])]
    assert live.unplaced(_snap_hops()[:4], _route_hops()) == []


def test_placing_adds_and_never_moves():
    route = _route_hops()
    placed = [{"hop": 2, "addresses": ["198.51.100.7"], "lat": 50.0, "lon": 8.0},
              {"hop": 5, "addresses": ["192.0.2.5"], "lat": 48.0, "lon": 11.0}]
    out = live.add_placed(route, placed)
    assert [h["hop"] for h in out] == [1, 2, 3, 4, 5]
    assert out[1]["lat"] == 12.0 and out[1]["addresses"] == ["192.0.2.2", "198.51.100.7"]
    assert out[4]["lat"] == 48.0


def test_compare_and_export_use_the_session_figures():
    route = {"hops": _route_hops(), "origin": {}}
    body = live.route_for_export(route, {"hops": _snap_hops()})
    assert body["hops"][2]["loss_pct"] == 40.0 and body["hops"][2]["min_rtt_ms"] == 12.0
    assert route["hops"][2]["loss_pct"] is None          # the placed route is not changed


def test_the_cli_table_marks_rate_limiting_and_counts_changes():
    snap = {"hops": _snap_hops(), "changes": [{"cycle": 9, "hop": 2, "kind": "address", "old": ["a"],
                                                "new": ["b"]}], "gaps": [{"from": 1, "to": 2}]}
    text = live.table_text(snap, {1: "Manila, PH"})
    lines = text.splitlines()
    assert lines[0].split()[:3] == ["#", "Host", "Loss%"] and "Manila, PH" in lines[1]
    assert "40.0*" in lines[3] and "rate limiting" in lines[-1] and "Path changes: 1." in lines[-1]
    assert "Gaps" in lines[-1]


@pytest.mark.parametrize("kind,expect", [("address", "instead of"), ("appeared", "started answering"),
                                         ("disappeared", "stopped answering"), ("destination", "destination")])
def test_every_change_kind_reads_as_a_sentence(kind, expect):
    old, new = (6, 5) if kind == "destination" else (["192.0.2.1"], ["192.0.2.9"])
    text = live.describe_change({"cycle": 4, "hop": 3, "kind": kind, "old": old, "new": new})
    assert text.startswith("Cycle 4:") and expect in text and chr(0x2014) not in text


# ---------------------------------------------------------- history cap --

def test_sessions_are_capped_by_size_oldest_first():
    traces = [{"route": {}, "when": i} for i in range(3)]
    sessions = [{"route": {}, "when": 10 + i, "session": {"blob": "x" * 1000}} for i in range(5)]
    newest_first = list(reversed(sessions)) + traces
    one = config._size(sessions[0])
    kept = config.cap_sessions(newest_first, limit=one * 3)
    assert [e["when"] for e in kept if e.get("session")] == [14, 13, 12]
    assert len([e for e in kept if not e.get("session")]) == 3      # traces are never dropped


def test_the_cap_is_fifty_megabytes():
    assert config.SESSIONS_MAX_BYTES == 50_000_000


@pytest.mark.parametrize("interval,expect", [(0.1, 1.0), (-1, 1.0), (float("nan"), 1.0), ("x", 1.0),
                                             (5, 5.0), (600, 60.0)])
def test_the_interval_setting_cannot_go_below_one_second(interval, expect):
    s = config.Settings()
    s.live_interval = interval
    assert config.normalise(s).live_interval == expect


@pytest.mark.parametrize("minutes,expect", [(0, 5), (60, 60), (10**9, 480), ("x", 60)])
def test_the_duration_setting_is_bounded(minutes, expect):
    s = config.Settings()
    s.live_duration_min = minutes
    assert config.normalise(s).live_duration_min == expect


# ------------------------------------------------------------- rebuilding --

def _session():
    return {"target": "example.net", "address": "192.0.2.6", "started": "2026-10-09T02:15:25Z",
            "ended": "2026-10-09T02:20:25Z", "interval_s": 1.0, "cycles": 300, "stopped_by": "user",
            "reached_hop": 6, "max_hops": 30, "duration_limit_s": 3600,
            "hops": [{"hop": 6, "addresses": ["192.0.2.6"], "sent": 300, "received": 297, "loss_pct": 1.0,
                      "last_ms": 30.0, "best_ms": 29.0, "avg_ms": 31.0, "worst_ms": 50.0, "stdev_ms": 2.0}],
            "changes": [{"cycle": 12, "at": "2026-10-09T02:15:37Z", "hop": 4, "kind": "address",
                         "old": ["192.0.2.4"], "new": ["198.51.100.4"]}],
            "gaps": [], "samples": {"hops": {"6": {"raw": [[0, 30.0], [1, None]], "buckets": []}}}}


def test_a_session_round_trips():
    s = imported.session(_session())
    assert s["cycles"] == 300 and s["hops"][0]["sent"] == 300 and s["changes"][0]["new"] == ["198.51.100.4"]
    assert s["loss"]["loss_pct"] == 1.0
    snap = live.saved_snapshot(s)
    assert snap["live"][6] == [(0, 30.0), (1, None)] and snap["changes"][0]["at"] > 0


@pytest.mark.parametrize("field,value", [
    ("address", "not an address"), ("address", None), ("address", 7),
])
def test_a_session_without_a_real_address_is_refused(field, value):
    data = _session()
    data[field] = value
    assert imported.session(data) is None


@pytest.mark.parametrize("hop", [
    {"hop": 6, "sent": 3, "received": 9},              # more received than sent
    {"hop": 6, "sent": -1, "received": 0},
    {"hop": 6, "sent": True, "received": 0},
    {"hop": "6", "sent": 3, "received": 3},
    {"hop": 900, "sent": 3, "received": 3},
    "a string",
])
def test_impossible_hops_are_dropped(hop):
    data = _session()
    data["hops"] = [hop]
    assert imported.session(data)["hops"] == []


def test_hostile_values_never_survive():
    data = _session()
    data["hops"][0].update(avg_ms=math.inf, worst_ms=-5, stdev_ms="9", loss_pct=150,
                           addresses=["<script>", "192.0.2.6", 7])
    data["changes"] = [{"cycle": 1, "hop": 1, "kind": "explode"}] + [
        {"cycle": i, "hop": 1, "kind": "address", "old": [], "new": []} for i in range(5000)]
    data["samples"]["hops"]["6"]["raw"] = [[i, 1.0] for i in range(100_000)] + [["x", 1]]
    data["target"] = "a" * 10_000
    s = imported.session(data)
    h = s["hops"][0]
    assert h["avg_ms"] is None and h["worst_ms"] is None and h["stdev_ms"] is None and h["loss_pct"] is None
    assert h["addresses"] == ["192.0.2.6"]
    assert len(s["changes"]) <= imported.SESSION_CHANGES and all(c["kind"] == "address" for c in s["changes"])
    assert len(s["samples"]["hops"]["6"]["raw"]) == imported.SESSION_RAW
    assert len(s["target"]) <= 253


def test_a_saved_annotation_is_not_trusted():
    data = _session()
    data["hops"][0]["annotations"] = ["ICMP rate limiting, not real loss"]
    assert imported.session(data)["hops"][0]["annotations"] == []


def test_a_newer_format_is_refused_clearly():
    with pytest.raises(imported.ImportRejected, match="newer Route Map"):
        imported.export({"format_version": 4, "route": {}})


def test_a_version_two_export_still_opens():
    from pathlib import Path
    olds = sorted((Path(__file__).parent / "fixtures" / "old_exports").glob("**/*.json"))
    assert olds
    for p in olds:
        doc = imported.export(imported.parse_json(p.read_text()))
        assert doc["route"] and doc.get("session") is None


def test_an_eight_hour_session_fits_the_file_cap():
    # One-minute buckets for 8 hours and 30 minutes of raw samples, 30 hops.
    hop = {"raw": [[float(t), 123.456] for t in range(1800)],
           "buckets": [{"t": t * 60, "sent": 60, "lost": 1, "min_ms": 120.001, "max_ms": 180.002,
                        "mean_ms": 130.003} for t in range(480)]}
    doc = {"session": {"samples": {"hops": {str(n): hop for n in range(1, 31)}}}}
    size = len((json.dumps(doc, indent=2) + "\n").encode())
    assert size < imported.MAX_FILE_BYTES, size


def test_a_three_megabyte_session_round_trips_through_a_file(tmp_path, monkeypatch):
    """A real session export of about 3 MB, written to disk and opened the way
    File > Open Trace opens it: the route and the plot data come back equal."""
    from concurrent.futures import Future

    from routemap_engine import probe, watch

    from routemap import service

    class SyncPool:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def submit(self, fn, *args):
            f = Future()
            f.set_result(fn(*args))
            return f

    monkeypatch.setattr(watch, "ThreadPoolExecutor", SyncPool)
    clock = {"t": 1_791_500_000.0, "m": 1000.0}

    def sleep(s):
        clock["t"] += s
        clock["m"] += s

    def fake(dst, ttl, seq, wait):
        if ttl == 30:
            return probe.Reply("192.0.2.30", 200.0 + (seq % 7), True)
        return probe.Reply(f"192.0.2.{ttl}", 5.0 * ttl + (seq % 5) * 0.1, False)
    w = watch.Watch("example.net", watch.WatchOptions(max_cycles=1500), probe_fn=fake,
                    resolve=lambda _t: "192.0.2.30", wall=lambda: clock["t"], mono=lambda: clock["m"], sleep=sleep)
    session = w.run()
    # Placed the way the window places a session: its own hops, offline sources.
    from routemap_engine import geo as _geo
    from routemap_engine.model import analyse_sync
    route = analyse_sync(watch.as_hops(session), (14.6, 121.0), sources=_geo.OFFLINE).to_dict()
    snap = live.snapshot(session)
    body = live.route_for_export(imported.route(route), snap)
    text = service.export_json(body, target="example.net", trace_text="", argv=["icmp", "watch"],
                               source="watch", origin_how="city", session=session.to_dict())
    path = tmp_path / "session.json"
    path.write_text(text, encoding="utf-8")
    size = path.stat().st_size
    assert 2_500_000 <= size <= 4_000_000, size                  # about 3 MB, under the 8 MB cap
    back = imported.export(imported.parse_json(imported.read_file(str(path))))
    assert back["route"] == imported.route(body)
    saved = session.to_dict()["samples"]["hops"]
    got = back["session"]["samples"]["hops"]
    assert set(got) == set(saved) and len(got) == 30
    for key in saved:
        assert got[key]["raw"] == saved[key]["raw"]
        assert got[key]["buckets"] == saved[key]["buckets"]
    assert back["session"]["cycles"] == 1500 and len(back["session"]["hops"]) == 30



def test_a_reopened_session_exports_and_reopens_again(tmp_path):
    """Export, reopen, export again, reopen again: the second trip used to fail,
    because a route placed from hops lost its parser label on the first import."""
    from routemap import service
    from routemap_engine import geo as _geo
    from routemap_engine.model import analyse_sync
    from routemap_engine.parse import Hop
    hops = [Hop(hop=n, addresses=[f"192.0.2.{n}"], rtts_ms=[4.0 * n], sent=10, lost=0) for n in range(1, 6)]
    route = analyse_sync(hops, (14.6, 121.0), sources=_geo.OFFLINE).to_dict()
    snap = {"hops": _snap_hops()}
    body = live.route_for_export(route, snap)
    for trip in range(3):
        text = service.export_json(body, target="x", trace_text="", argv=None, source="watch", origin_how=None,
                                   session=_session())
        back = imported.export(imported.parse_json(text))
        assert back["route"]["parser"] == "hops" and back["route"]["parser_label"] == "hops", trip
        body = back["route"]


def test_a_session_export_route_matches_the_schema_exactly():
    import jsonschema
    from routemap_engine import geo as _geo
    from routemap_engine.model import analyse_sync
    from routemap_engine.parse import Hop
    hops = [Hop(hop=n, addresses=[f"192.0.2.{n}"], rtts_ms=[4.0 * n], sent=10, lost=0) for n in range(1, 6)]
    route = analyse_sync(hops, (14.6, 121.0), sources=_geo.OFFLINE).to_dict()
    body = live.route_for_export(route, {"hops": _snap_hops()})
    jsonschema.validate(body, imported._schema())
    assert body["hops"][2]["loss_pct"] == 40.0 and "best_ms" not in body["hops"][2]
