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

HERE = pathlib.Path(__file__).parent / "fixtures" / "routemap"


class _AsnDb:
    """The offline ASN database's answers for the networks on these paths."""
    def lookup(self, addr):
        from types import SimpleNamespace
        if addr in ("198.51.100.1", "198.51.100.2"):          # the home routers
            return None
        rows = (("198.51.100.", 9299), ("203.0.113.", 9299), ("62.115.", 1299),
                ("5.56.18.114", 201011), ("82.98.", 12306), ("193.99.", 12306), ("212.19.", 12306))
        for prefix, asn in rows:
            if addr.startswith(prefix):
                return SimpleNamespace(asn=asn, org={9299: "Philippine Long Distance Telephone Company",
                                                     1299: "Arelion Sweden AB", 201011: "Core-Backbone GmbH",
                                                     12306: "Plus.line AG"}[asn], network="") if asn else None
        return None


def _load(name):
    """A fixture route with its AS numbers added the way the app adds them
    (insight.offline): the fixtures carry none, so a lookup that misses a
    path's hops shows here (ODIN test build 4: "No AS numbers on any path")."""
    from routemap import config, insight
    route = json.loads((HERE / name).read_text())["route"]
    real = insight._asn_reader
    insight._asn_reader = lambda: _AsnDb()
    try:
        insight.offline(route, config.Settings(online_lookups=False))
    finally:
        insight._asn_reader = real
    return route


ROUTE = _load("odin_paths_run3_route.json")
PATHS = ROUTE["paths"]["paths"]
RUN4 = _load("odin_paths_run4_route.json")


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
    assert any("FR" in [c.get("cc") for c in cs] for _, cs in groups)
    assert not any("US" in [c.get("cc") for c in cs] for _, cs in groups)


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


def test_9_a_run_stopped_at_the_cap_says_so_and_reports_the_total():
    """ODIN test build 5: "stopped at the 1,450-probe cap" under a cap of
    1,500. The total is reported as such; the cap is named as the cap."""
    disc = RUN4["paths"]
    head = cli._paths_text(RUN4).splitlines()[0]
    assert f"{disc['probes_sent']:,} probes in" in head
    assert (f"discovery stopped at {disc['discovery_probes']:,} probes to leave room for target attempts "
            f"within the {disc['budget']:,} cap; more paths may exist") in head
    assert "-probe cap" not in head


def test_9_the_window_heading_uses_the_same_words(app):
    from routemap.gui.mainwindow import MainWindow
    w = MainWindow()
    w.show_result(RUN4, "heise.de", ["tcp-paris", "heise.de"])
    text = w.summary.text().replace("&nbsp;", " ")
    assert f"discovery stopped at {RUN4['paths']['discovery_probes']:,} probes to leave room" in text
    w.close()


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


def test_a_every_router_on_a_path_has_its_asn_and_the_summary_lists_the_as_paths():
    rows = path_rows(RUN4["hops"], RUN4["paths"]["paths"])
    subs = [r for r in rows if r.get("_sub")]
    assert subs and all(r.get("asn") for r in subs if r.get("address") not in ("198.51.100.1", "198.51.100.2")), \
        [(r["hop"], r.get("_sub"), r.get("address"), r.get("asn")) for r in subs if not r.get("asn")]
    for row in rows:
        if row.get("_summary"):
            assert row.get("asn") or row.get("_asn_text") == "mixed", row["hop"]
    groups = pathsummary.as_paths(RUN4)
    assert groups and all(steps for _, steps in groups)
    assert {s["asn"] for _, steps in groups for s in steps} >= {1299, 12306}


def test_b_the_note_states_how_many_attempts_each_path_got():
    from routemap.gui.hoptable import path_notes
    disc = json.loads(json.dumps(RUN4["paths"]))
    note = next(n for n in path_notes(disc) if n.startswith("Target answered"))
    assert "of ten connection attempts" in note
    for p in disc["paths"]:
        if p["reached"]:
            p["sent"] = 7
    note = next(n for n in path_notes(disc) if n.startswith("Target answered"))
    assert "of 7 connection attempts" in note and "budget ran out" in note


def test_c_countries_never_skip_hops_without_saying_so():
    """Paths B, I, N and P read "PH (origin) > PH > DE" in the app: nothing
    between Asia and Europe had a place on those paths."""
    for ids, items in pathsummary.countries(RUN4, origin_cc="PH"):
        members = [p for p in RUN4["paths"]["paths"] if p["id"] in _expand(ids)]
        for p in members:
            placed = [h for h in sorted(p["located"], key=lambda h: h["hop"])
                      if h.get("lat") is not None and h.get("source") != "local"]
            for a, b in zip(placed, placed[1:]):
                between = [h for h in p["located"] if a["hop"] < h["hop"] < b["hop"]]
                if a.get("cc") != b.get("cc") and between:
                    i_a = next(i for i, c in enumerate(items) if c.get("cc") == a["cc"])
                    assert "gap" in items[i_a + 1], (p["id"], items)


def test_9_the_pdf_uses_the_same_words(app, tmp_path):
    from PySide6.QtPdf import QPdfDocument
    from routemap import config
    from routemap.gui.app import write_export
    write_export("pdf", str(tmp_path / "r.pdf"), {"route": RUN4, "target": "heise.de", "source": "paths",
                                                  "trace_text": "", "argv": ["tcp-paris"]},
                 settings=config.Settings(online_lookups=False))
    doc = QPdfDocument()
    doc.load(str(tmp_path / "r.pdf"))
    text = " ".join(doc.getAllText(i).text() for i in range(doc.pageCount())).replace("\n", " ")
    assert (f"discovery stopped at {RUN4['paths']['discovery_probes']:,} probes to leave room for target "
            f"attempts within the {RUN4['paths']['budget']:,} cap") in " ".join(text.split())
