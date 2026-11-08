"""The adapter a trace went through, in exports and history (0.5.0-beta.5).

The export stays format 5 with optional keys, on the condition that the reader
released in 0.5.0-beta.4 accepts it. That reader and engine 0.8.2's schema are
exact copies of the released files (tests/fixtures/released/), checked by their
git blob hashes, because CI checks out without tags."""
import asyncio
import hashlib
import importlib.util
import json
import pathlib
import sys

import pytest

from routemap import config, imported, netnotes, service
from routemap_engine import OFFLINE, analyse_paths, analyse_sync, multipath
from routemap_engine.probe import FlowAnswer

RELEASED = pathlib.Path(__file__).parent / "fixtures" / "released"
BLOBS = {"imported_0_5_0b4.py.txt": "091136e8ff192d671290193d31095d82ff4a49ac",           # v0.5.0-beta.4:routemap/imported.py
         "route.schema-engine-0.8.2.json": "67dd8355182a1f1e4cf4fb84adaa3d7bef1fdc75"}    # engine v0.8.2
TEXT = "traceroute to x (203.0.113.9), 30 hops max\n 1  192.0.2.1  1.0 ms\n 2  203.0.113.9  5.0 ms\n"
BLOCK = {"kind": "tunnel", "label": "Corp tunnel", "selected": False, "check": None, "description": "A driver",
         "addresses": ["198.51.100.2"], "gateways": ["198.51.100.1"]}


def _blob(path):
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


@pytest.fixture(scope="module")
def reader_b4():
    for name, blob in BLOBS.items():
        assert _blob(RELEASED / name) == blob, f"{name} is not the released file"
    spec = importlib.util.spec_from_loader("imported_b4", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile((RELEASED / "imported_0_5_0b4.py.txt").read_text("utf-8"), "imported_b4", "exec"), module.__dict__)
    old_schema = json.loads((RELEASED / "route.schema-engine-0.8.2.json").read_text("utf-8"))
    module._schema = lambda: old_schema          # what 0.5.0-beta.4 shipped with
    sys.modules["imported_b4"] = module
    return module


class Lab:
    METHOD = "tcp-paris"

    def __init__(self):
        self.t, self.queue = 1000.0, []

    def clock(self):
        return self.t

    def send(self, flow, ttl, seq):
        at = self.t + 0.002
        self.queue.append((at, FlowAnswer(seq, "203.0.113.9", True, at, "completed") if ttl >= 2 or flow >= 64 else
                           FlowAnswer(seq, "192.0.2.1", False, at)))

    def read(self, timeout):
        due = [q for q in self.queue if q[0] <= self.t + timeout]
        self.queue = [q for q in self.queue if q[0] > self.t + timeout]
        self.t += timeout if not due else 0.0
        if due:
            self.t = max(self.t, max(d[0] for d in due))
        return [a for _, a in due]

    def close(self):
        pass


def paths_route():
    lab = Lab()
    d = multipath.Discoverer("example.net", "203.0.113.9", lab, clock=lab.clock, check_interception=True,
                             icmp_check=lambda ttl: None, options=multipath.Options(budget=200)).run()
    assert d.interception["intercepted"] is True
    return asyncio.run(analyse_paths(d, (14.6, 121.0), sources=OFFLINE))


def export(route, **kw):
    return json.loads(service.export_json(route, target="example.net", trace_text="x", argv=["icmp"],
                                          source="local", origin_how="ip", **kw))


def test_the_export_stays_format_5():
    assert service.EXPORT_FORMAT_VERSION == imported.FORMAT_VERSION == 5


@pytest.mark.parametrize("addresses", [False, True])
def test_beta4_reader_accepts_format_5_with_the_new_keys(reader_b4, addresses):
    assert reader_b4.FORMAT_VERSION == 5
    route = paths_route()
    doc = export(route, interface=BLOCK, include_interface_addresses=addresses)
    assert doc["interface"]["kind"] == "tunnel" and doc["route"]["paths"]["interception"]["intercepted"] is True
    assert ("addresses" in doc["interface"]) is addresses
    out = reader_b4.export(doc)
    assert out["route"]["hops"] == reader_b4.export(export(route))["route"]["hops"]
    assert out["route"]["paths"]["method"] == "tcp-paris"
    assert "interface" not in out and "interception" not in out["route"]["paths"]


def test_beta4_reader_accepts_a_plain_trace_with_the_interface_block(reader_b4):
    out = reader_b4.export(export(analyse_sync(TEXT, sources=OFFLINE), interface=BLOCK))
    assert len(out["route"]["hops"]) == 2


def test_an_export_carries_kind_and_label_only_unless_asked():
    route = analyse_sync(TEXT, sources=OFFLINE)
    plain = export(route, interface=BLOCK)["interface"]
    assert plain == {"kind": "tunnel", "label": "Corp tunnel", "selected": False, "check": None}
    assert "198.51.100" not in json.dumps(export(route, interface=BLOCK))
    asked = export(route, interface=BLOCK, include_interface_addresses=True)["interface"]
    assert asked["addresses"] == ["198.51.100.2"] and asked["gateways"] == ["198.51.100.1"]


def test_an_unclassified_adapter_is_in_the_export():
    route = analyse_sync(TEXT, sources=OFFLINE)
    assert export(route, interface={**BLOCK, "kind": "unclassified"})["interface"]["kind"] == "unclassified"


def test_no_block_no_key():
    assert "interface" not in export(analyse_sync(TEXT, sources=OFFLINE))


def test_this_version_rebuilds_the_block_and_drops_a_files_addresses():
    doc = export(analyse_sync(TEXT, sources=OFFLINE), interface=BLOCK, include_interface_addresses=True)
    got = imported.export(doc)["interface"]
    assert got == {"kind": "tunnel", "label": "Corp tunnel", "selected": False, "check": None}


def test_interception_survives_a_round_trip():
    doc = export(paths_route(), interface=BLOCK)
    found = imported.export(doc)["route"]["paths"]["interception"]
    assert found["intercepted"] is True and found["condition"].startswith("connect_completed_at_ttl_")


@pytest.mark.parametrize("bad", [None, "x", {}, {"kind": "vpn", "label": "x"}, {"kind": "tunnel"},
                                 {"kind": "tunnel", "label": 5}, {"kind": "tunnel", "label": "\x00"}])
def test_a_malformed_block_is_dropped(bad):
    doc = export(analyse_sync(TEXT, sources=OFFLINE))
    doc["interface"] = bad
    assert imported.export(doc)["interface"] is None


def test_a_bad_check_is_read_as_none():
    assert imported.interface({"kind": "tunnel", "label": "x", "check": "nope"})["check"] is None


def test_history_keeps_no_local_addresses():
    route = analyse_sync(TEXT, sources=OFFLINE).to_dict()
    entry = config.history_entry(route, target="x", trace_text=TEXT, argv=["icmp"], source="local")
    entry["interface"] = netnotes.stored(BLOCK)
    settings = config.Settings()
    config.add_history(entry, settings)
    assert "198.51.100" not in config.history_path().read_text("utf-8")
    assert config.load_history()[0]["interface"]["label"] == "Corp tunnel"
