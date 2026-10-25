"""ODIN, 26 Oct 2026 (Phase 2 test build): Paths to heise.de reached the
target at full TTL on 2 of 16 paths, yet the other 14, whose ten attempts
each went unanswered, were listed "not reached; last answer hop 13". With the
target proven alive in the same run that is a server answering fewer after
the discovery's probes; "not reached" is kept for a run where no path got
there. Every view is checked: the path list, the CLI, the PDF's table, the
map legend, the route summary and the notes."""
import copy
import json
import pathlib

import pytest

from routemap import pathsummary, probes
from routemap.gui import hoptable

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "gui" / "odin_paths_080dev1_route.json"


def _discovery(reached_ids, method="tcp-paris"):
    """ODIN's run with only *reached_ids* reached at full TTL; every other
    path sent its ten attempts and got no answer, as on 26 Oct."""
    disc = copy.deepcopy(json.loads(FIXTURE.read_text())["route"]["paths"])
    disc["method"] = method
    for p in disc["paths"]:
        if p["id"] not in reached_ids:
            p.update(reached=False, reached_by=None, sent=10, lost=10, loss_pct=100.0, rtt_to_target_ms=None,
                     silent=None)
    return disc


def _views(disc):
    """Every text a discovery's paths are shown in."""
    paths = disc["paths"]
    out = []
    for p in paths:
        out += [hoptable.rtt_cell(p, disc), hoptable.target_cell(p, disc), hoptable.target_cell(p, disc, True),
                hoptable.legend_text(p, disc)]
    out += [pathsummary.target_summary(disc)] + probes.paths_lines(disc) + hoptable.path_notes(disc)
    return out


@pytest.mark.parametrize("method", ["tcp-paris", "icmp-paris"])
@pytest.mark.parametrize("reached", [{"A", "B"}, {"P"}, {"A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K",
                                                       "L", "M", "N", "O"}])
def test_a_path_without_answers_is_not_called_unreached_when_the_target_answered(method, reached):
    disc = _discovery(reached, method)
    texts = _views(disc)
    assert not [t for t in texts if "not reached" in t], [t for t in texts if "not reached" in t]
    silent = [p for p in disc["paths"] if p["id"] not in reached]
    if method == "tcp-paris":
        assert all(hoptable.target_cell(p, disc) == "0 of 10" for p in silent)
    else:
        assert all(hoptable.target_cell(p, disc) == "100% (10 of 10)" for p in silent)
    joined = " ".join(probes.paths_lines(disc))
    assert "some servers answer fewer after the discovery's probes" in joined
    assert f"On {len(disc['paths'])} paths the target answered 0" in joined or \
        f"On {len(silent)} paths the target answered 0 of 10 attempts each" in joined


def test_not_reached_stays_for_a_run_where_no_path_got_there():
    disc = _discovery(set())
    for p in disc["paths"]:
        assert hoptable.rtt_cell(p, disc) == "not reached"
        assert hoptable.target_cell(p, disc).startswith("not reached")
        assert hoptable.legend_text(p, disc) == "not reached"
    assert pathsummary.target_summary(disc).startswith("not reached")
    assert "The target was then asked at full TTL: not reached." in " ".join(probes.paths_lines(disc)) or \
        disc.get("stopped_by") != "gap"


def test_the_cli_and_the_pdf_use_the_same_words():
    from routemap import cli
    from routemap.gui import report
    disc = _discovery({"A", "B"})
    route = copy.deepcopy(json.loads(FIXTURE.read_text())["route"])
    route["paths"] = disc
    text = cli._paths_text(route)
    assert "not reached" not in text and "0 of 10" in text
    texts = []

    class Flow:
        def heading(self, t, *a, **k): texts.append(t)
        def text(self, t, *a, **k): texts.append(t)
        def table(self, headers, rows, *a, **k): texts.extend(" ".join(map(str, r)) for r in rows)
    report._paths_section(Flow(), route)
    assert texts and not [t for t in texts if "not reached" in t]
    assert sum("0 of 10" in t for t in texts) == 14


def test_the_pdf_prints_the_differences_every_path_shares_once():
    """ODIN, 26 Oct 2026: 16 rows each repeating the same "Differs at" hops."""
    disc = _discovery({"A", "B"})
    shared, rest = hoptable.shared_differences(hoptable.path_differences(disc["paths"]))
    assert [h["hop"] for h in shared] == [4, 5, 6, 13]        # home and ISP, then Frankfurt on all
    full = hoptable.path_differences(disc["paths"])
    for pid, entries in full.items():                # nothing lost: shared and the rest make the whole
        assert {(h["hop"], hoptable._place(h)) for h in entries} == \
            {(h["hop"], hoptable._place(h)) for h in shared + rest[pid]}
        assert not {h["hop"] for h in rest[pid]} & {4, 5, 6, 13}
