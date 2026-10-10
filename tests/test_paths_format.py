"""Export format 4 (0.4.0): paths, a reverse trace and the address family
survive a round trip; versions 1 to 3 still open; and the released 0.3.0
reader meets a version 4 file the way it should, with "Made by a newer Route
Map", not a broken half-route.

The 0.3.0-beta.1 reader and engine 0.6.0's schema are exact copies of the
released files (tests/fixtures/released/), checked by their git blob hashes,
because CI checks out without tags."""
import asyncio
import hashlib
import importlib.util
import json
import pathlib
import sys

import pytest

from routemap import imported, service
from routemap_engine import OFFLINE, analyse_paths, analyse_sync, multipath

HERE = pathlib.Path(__file__).parent
RELEASED = HERE / "fixtures" / "released"
BLOBS = {"imported_0_3_0b1.py.txt": "b5c082d1d50b67f3712beb3845731a38201d4eb5",   # v0.3.0-beta.1:routemap/imported.py
         "route.schema-engine-0.6.0.json": "a1c168289d02f922acdf2bf93fc4ce06529e35a0"}  # engine v0.6.0


def _blob(path):
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


@pytest.fixture(scope="module")
def reader_030():
    for name, blob in BLOBS.items():
        assert _blob(RELEASED / name) == blob, f"{name} is not the released file"
    spec = importlib.util.spec_from_loader("imported_030", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile((RELEASED / "imported_0_3_0b1.py.txt").read_text("utf-8"), "imported_030", "exec"),
         module.__dict__)
    old_schema = json.loads((RELEASED / "route.schema-engine-0.6.0.json").read_text("utf-8"))
    module._schema = lambda: old_schema          # what 0.3.0 shipped with: engine 0.6.0
    sys.modules["imported_030"] = module
    return module




class _Lab:
    """A two-branch network on a virtual clock (the engine's lab, in brief)."""
    def __init__(self, route_of):
        self.route_of, self.t, self.queue = route_of, 1000.0, []

    def clock(self):
        return self.t

    def send(self, flow, ttl, seq):
        from routemap_engine.probe import FlowAnswer
        r = self.route_of(flow)
        hop = r[min(ttl, len(r)) - 1]
        self.queue.append((self.t + 0.005 * ttl, FlowAnswer(seq, hop, ttl >= len(r), self.t + 0.005 * ttl)))

    def read(self, timeout):
        due = [q for q in self.queue if q[0] <= self.t + timeout]
        self.queue = [q for q in self.queue if q[0] > self.t + timeout]
        self.t += timeout if not due else 0.0
        if due:
            self.t = max(self.t, max(d[0] for d in due))
        return [a for _, a in due]

    def close(self):
        pass


def paths_route(v6=False):
    pre = "2001:4860:0:1::" if v6 else "203.0.113."
    a = [f"{pre}{n}" for n in (1, 2, 3, 4, 9)]
    dst = a[-1]
    lab = _Lab(lambda flow: [a[0], a[1] if flow % 2 else a[2], a[3], dst])
    d = multipath.Discoverer("example.net", dst, lab, clock=lab.clock).run()
    return asyncio.run(analyse_paths(d, (14.6, 121.0), sources=OFFLINE)), d


def _export(route, reverse=None):
    return json.loads(service.export_json(route, target="example.net", trace_text="x", argv=["icmp"],
                                          source="local", origin_how="ip", reverse=reverse))


def test_every_0_4_0_export_is_version_4_with_its_family():
    route, _ = paths_route()
    doc = _export(route)
    assert doc["format_version"] == service.EXPORT_FORMAT_VERSION == imported.FORMAT_VERSION == 4
    assert doc["af"] == 4 and _export(paths_route(v6=True)[0])["af"] == 6


def test_released_0_3_0_reader_refuses_a_version_4_export_as_made_by_a_newer_route_map(reader_030):
    route, _ = paths_route()
    for doc in (_export(route), _export(analyse_sync("traceroute to x (192.0.2.9), 30 hops max\n"
                                                      " 1  192.0.2.9  1.0 ms\n", sources=OFFLINE))):
        with pytest.raises(reader_030.NewerFormat) as exc:
            reader_030.export(doc)
        assert exc.value.title == "Made by a newer Route Map"
        assert exc.value.message.startswith("This export is format version 4, made by a newer Route Map.")


def test_version_4_round_trips_paths_reverse_and_ipv6():
    route, d = paths_route(v6=True)
    rev = analyse_sync("traceroute to you (2001:4860:0:7::7), 30 hops max\n 1  2001:4860:0:1::9  1.0 ms\n"
                       " 2  2001:4860:0:7::7  9.0 ms\n", sources=OFFLINE)
    reverse = {"measurement_id": 123456789, "af": 6, "trace_text": "t", "route": rev,
               "probe": {"id": 6012, "asn": 12306, "country": "de", "distance_km": 4.0, "lat": 52.4, "lon": 9.7}}
    got = imported.export(_export(route, reverse))
    assert len(got["route"]["paths"]["paths"]) == len(d.paths) == 2
    assert got["route"]["paths"]["paths"][0]["hops"] == d.paths[0].hops
    assert got["reverse"]["probe"] == {"id": 6012, "asn": 12306, "country": "DE", "distance_km": 4.0,
                                       "lat": 52.4, "lon": 9.7}
    assert got["reverse"]["af"] == 6 and [h["hop"] for h in got["reverse"]["route"]["hops"]] == [1, 2]


def test_paths_in_a_file_are_held_to_their_limits():
    route, _ = paths_route()
    doc = _export(route)
    many = doc["route"]["paths"]["paths"] * 20
    for i, p in enumerate(many):
        p = dict(p, id="ABCDEFGHIJKLMNOP"[i % 16])
        many[i] = p
    doc["route"]["paths"]["paths"] = many
    doc["route"]["paths"]["paths"][0]["hops"] = ["203.0.113.1"] * 100
    got = imported.export(doc)["route"]["paths"]
    assert len(got["paths"]) == 16 and len(got["paths"][0]["hops"]) == 30
    doc["route"]["paths"]["method"] = "udp-whatever"
    assert "paths" not in imported.export(doc)["route"]


@pytest.mark.parametrize("version", [1, 2, 3])
def test_versions_1_to_3_still_open(version):
    route = analyse_sync("traceroute to x (192.0.2.9), 30 hops max\n 1  192.0.2.9  1.0 ms\n", sources=OFFLINE)
    doc = _export(route)
    doc["format_version"] = version
    doc.pop("af")
    assert imported.export(doc)["route"]["hops"][0]["address"] == "192.0.2.9"


def test_a_0_4_0_history_entry_read_by_0_3_0_drops_what_it_does_not_know(reader_030):
    route, _ = paths_route()
    entry = {"route": route.to_dict(), "target": "example.net", "when": 1_791_500_000.0, "hops": 4,
             "placed": 0, "tool": "icmp", "source": "local",
             "reverse": {"measurement_id": 1, "route": route.to_dict()}}
    old = reader_030.history_entry(entry)
    assert old is not None and "paths" not in old["route"] and "reverse" not in old
