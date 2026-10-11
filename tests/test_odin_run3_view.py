"""ODIN, 12 Oct 2026 (0.4.0-beta.2 test build): the CLI passed; the app's
Trace and Paths views did not. tests/fixtures/routemap/odin_paths_run3_route.json
is run 3 replayed through the engine with the names and places it showed
(hops 1 to 6 documentation addresses), stopped at the probe cap as the app's
run was. One test per point of the review; each failed on the test build."""
import json
import pathlib

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from routemap import cli, pathsummary
from routemap.gui.hoptable import HopTable, legend_text, path_rows

ROUTE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "routemap" / "odin_paths_run3_route.json")
                   .read_text())["route"]
PATHS = ROUTE["paths"]["paths"]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _table(app):
    t = HopTable()
    t.set_hops(ROUTE["hops"], paths=PATHS)
    return t, t.model_


def test_2_a_cut_cell_shows_its_full_text_on_hover(app):
    t, m = _table(app)
    assert t.textElideMode() == Qt.ElideRight
    col = m.keys.index("place")
    row = next(i for i, h in enumerate(m.hops) if (h.get("place") or "").startswith("Frankfurt am Main"))
    tip = m.data(m.index(row, col), Qt.ToolTipRole)
    assert "Frankfurt am Main, DE" in tip.split("<br>")[0]
    notes = m.keys.index("notes")
    noted = next(i for i, h in enumerate(m.hops) if h.get("annotations"))
    assert m.hops[noted]["annotations"][0] in m.data(m.index(noted, notes), Qt.ToolTipRole).split("<br>")[0]


def test_3_the_target_is_summarised_per_path_not_as_one_trace():
    text = pathsummary.target_summary(ROUTE["paths"])
    assert "persists" not in text and "not reached:" in text
    unreached = [p["id"] for p in PATHS if not p["reached"]]
    from routemap.gui.hoptable import letters
    assert f"not reached: {letters(unreached)}" in text


def test_4_each_as_path_is_one_paths_with_its_letters():
    groups = pathsummary.as_paths(ROUTE)
    assert len(groups) > 1
    taken = sorted(i for ids, _ in groups for i in ids.replace("-", " ").split())
    for ids, steps in groups:
        members = [p for p in PATHS if p["id"] in _expand(ids)]
        for p in members:
            mine = [s["asn"] for s in __import__("routemap_engine").osint.as_path({"hops": p["located"]})]
            assert mine == [s["asn"] for s in steps], (p["id"], mine, steps)
    assert taken


def test_5_countries_per_path_keep_france():
    groups = pathsummary.countries(ROUTE)
    assert any("FR" in [c["cc"] for c in cs] for _, cs in groups)
    assert not any("US" in [c["cc"] for c in cs] for _, cs in groups)


def test_6_the_legend_speaks_as_the_path_list():
    disc = ROUTE["paths"]
    for p in PATHS:
        text = legend_text(p, disc)
        if not p["reached"]:
            assert text == "not reached"
        else:
            assert "% loss" not in text


def test_7_a_split_row_mixes_no_routers():
    rows = path_rows(ROUTE["hops"], PATHS)
    for row in rows:
        if row.get("_summary"):
            assert row.get("min_rtt_ms") is None and row.get("avg_rtt_ms") is None, row["hop"]
            subs = [r for r in rows if r["hop"] == row["hop"] and r.get("_sub")]
            asns = {s.get("asn") for s in subs}
            assert (row.get("asn") == asns.pop()) if len(asns) == 1 else row.get("_asn_text") == "mixed"


def test_8_a_sub_row_names_its_source_as_its_row_does(app):
    from routemap.gui.mapview import source_label
    rows = path_rows(ROUTE["hops"], PATHS)
    labels = {}
    for r in rows:
        if r.get("source") == "ip-db" and r.get("address") and not r.get("_summary"):
            labels.setdefault(r["address"], set()).add(source_label(r))
    assert labels and all(len(v) == 1 for v in labels.values()), labels


def test_9_a_run_stopped_at_the_cap_says_so():
    out = cli._paths_text(ROUTE)
    assert "1,500 probes" in out and "stopped at the 1,500-probe cap; more paths may exist" in out.splitlines()[0]


def _expand(ids):
    from routemap.gui.hoptable import PATH_LETTERS
    out = []
    for tok in ids.split():
        if "-" in tok:
            a, b = tok.split("-")
            out += list(PATH_LETTERS[PATH_LETTERS.index(a):PATH_LETTERS.index(b) + 1])
        else:
            out.append(tok)
    return out


def test_10_the_windows_path_list_rows_are_short_and_say_where_unreached_paths_ended(app):
    from routemap.gui.panels import PathsPanel
    panel = PathsPanel()
    panel.set_paths(ROUTE["paths"], ROUTE["hops"])
    for i in range(panel.list.topLevelItemCount()):
        item = panel.list.topLevelItem(i)
        p = PATHS[i]
        assert all(len(item.text(c)) <= 48 for c in range(5)), [item.text(c) for c in range(5)]
        if not p["reached"]:
            assert item.text(3) == "not reached" and item.text(4).startswith("last answer: hop ")
            assert "not reached; last answer hop" in item.toolTip(4)
        if i:
            assert "Differs at" in item.toolTip(2)


def test_2_text_columns_fit_their_text(app):
    t, m = _table(app)
    for key in ("place", "source"):
        col = m.keys.index(key)
        assert t.columnWidth(col) >= min(t.sizeHintForColumn(col), HopTable.FIT_MAX)
