"""How a discovery like ODIN's (11 Oct 2026, 0.4.0-beta.1) is shown: sixteen
paths split at one hop, a home router answering every other probe, a TCP
discovery. Each test is a fault that run printed; each failed on the code
that printed it."""
import asyncio
import re

import pytest

from routemap import cli
from routemap.gui.hoptable import path_differences, path_rows
from routemap_engine import analyse_paths, multipath
from routemap_engine.geo import Sources
from routemap_engine.probe import FlowAnswer

DST = "198.18.0.9"
SPLIT = [f"198.18.3.{i}" for i in range(16)]


class Lab:
    """Hop 1 answers every other probe; hop 3 balances over 16 routers by
    flow; the target is hop 5. TCP, as on Windows."""
    METHOD = "tcp-paris"

    def __init__(self):
        self.t, self.queue, self.home = 1000.0, [], 0

    def clock(self):
        return self.t

    def send(self, flow, ttl, seq):
        if ttl == 1:
            self.home += 1
            if self.home % 2 == 0:
                return True
        hop = min(ttl, 5)
        addr = ["198.51.100.1", "198.18.2.1", SPLIT[flow % 16], "198.18.4.1", DST][hop - 1]
        rtt = 0.002 * hop + 0.2 * (hop >= 3)
        self.queue.append((self.t + rtt, FlowAnswer(seq, addr, hop == 5, self.t + rtt)))
        return True

    def read(self, timeout):
        due = [q for q in self.queue if q[0] <= self.t + timeout]
        self.queue = [q for q in self.queue if q[0] > self.t + timeout]
        self.t = max(self.t + (0 if due else timeout), max((d[0] for d in due), default=0))
        return [a for _, a in due]

    def close(self):
        pass


@pytest.fixture(scope="module")
def route():
    lab = Lab()
    d = multipath.Discoverer("example.test", DST, lab, clock=lab.clock).run()
    r = asyncio.run(analyse_paths(d, (14.6, 121.0), sources=Sources(hoiho=None, ip_db=None, ptr=None)))
    return r.to_dict()


def test_1_a_hop_some_paths_did_not_answer_is_no_difference(route):
    paths = route["paths"]["paths"]
    assert len(paths) == 16
    for pid, entries in path_differences(paths).items():
        assert [h["hop"] for h in entries] == [3], (pid, entries)
    out = cli._paths_text(route)
    assert "hop 1" not in out.split("Differs at")[1]


def test_4_a_split_hop_is_summarised_once_and_flows_count_against_all_used(route):
    rows = path_rows(route["hops"], route["paths"]["paths"])
    hop3 = [r for r in rows if r["hop"] == 3]
    main, subs = hop3[0], hop3[1:]
    assert main.get("_summary") == "16 routers" and len(subs) == 16
    assert {s["address"] for s in subs} == set(SPLIT)
    out = cli._paths_text(route)
    used = route["paths"]["flows"]
    assert re.search(rf"\bA\s+\d+ of {used}\b", out), out


def test_6_tcp_counts_what_the_target_answered_not_path_loss(route):
    out = cli._paths_text(route)
    assert "Target answered" in out and "Loss to target" not in out
    assert re.search(r"\b10 of 10\b", out)


def test_7_columns_line_up_however_many_paths_pass_a_hop(route):
    out = cli._paths_text(route).splitlines()
    head = next(i for i, line in enumerate(out) if line.lstrip().startswith("#"))
    table = out[head:out.index("", head)]
    start = table[0].index("Address")
    for line in table[1:]:
        cell = line[start:].split()[0] if len(line) > start else ""
        assert line[start - 2:start] == "  " and cell, (line, start)
