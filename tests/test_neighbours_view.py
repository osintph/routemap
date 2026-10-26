"""A hop inferred from its neighbours (routemap-engine 0.8.0) is shown as such
everywhere: Source "inferred from neighbours", a hollow marker on the map and
in the table, a legend entry, the same words in the PDF, and source
"neighbours" in the JSON. ODIN, heise.de, 26 Oct 2026: 62.115.153.153
(Arelion's link to Plus.line, no site code, DB-IP's Chicago ruled out)
between two Frankfurt hops. tests/fixtures/gui/odin_paths_neighbours_route.json."""
import json
import pathlib

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from routemap.gui import mapview, theme  # noqa: E402

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "gui" / "odin_paths_neighbours_route.json"
DATA = json.loads(FIXTURE.read_text())
ROUTE = DATA["route"]
ADDR = "62.115.153.153"


def _hop():
    return next(h for h in ROUTE["hops"] if h.get("address") == ADDR)


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_the_fixture_has_the_inferred_hop():
    hop = _hop()
    assert hop["source"] == "neighbours" and hop["place"] == "Frankfurt, DE"
    assert hop["reason"].startswith("inferred from neighbours")


def test_the_map_draws_it_hollow_on_its_own(app):
    groups = mapview.route_groups(ROUTE)
    mine = [g for g in groups if any(h.get("address") == ADDR for h in g["hops"])]
    assert mine and all(g["inferred"] for g in mine)
    assert all(not any(h.get("source") != "neighbours" for h in g["hops"]) for g in mine)   # not merged
    assert mapview.source_label(_hop()) == "inferred from neighbours"


def test_the_window_table_map_and_legend(app):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    from routemap.gui.mainwindow import MainWindow
    w = MainWindow()
    w.show_result(ROUTE, "heise.de", ["tcp-paris", "heise.de"], trace_text=DATA["trace_text"])
    app.processEvents()
    model = w.table.model()
    src = next(c for c in range(model.columnCount()) if model.headerData(c, Qt.Horizontal) == "Source")
    row = next(r for r in range(model.rowCount())
               if ADDR in str(model.data(model.index(r, next(c for c in range(model.columnCount())
                                                               if model.headerData(c, Qt.Horizontal) == "IP address")))))
    assert model.data(model.index(row, src)) == "inferred from neighbours"
    icon = model.data(model.index(row, src), Qt.DecorationRole)
    source_model = getattr(model, "sourceModel", lambda: model)()
    assert icon is not None and icon.cacheKey() == source_model.icons["neighbours"].cacheKey()
    markers = [m for m in w.map.flat.items_ if getattr(m, "hollow", False) and not getattr(m, "silent", False)]
    assert markers, "no hollow marker"
    legend = " ".join(c.text() for c in w.map.flat.legend.findChildren(QLabel))
    assert theme.SOURCE_LABELS["neighbours"] in legend
    w.close()


def test_the_pdf_and_the_json_say_so(app, tmp_path):
    from PySide6.QtPdf import QPdfDocument

    from routemap.gui.app import write_export
    current = {"route": ROUTE, "target": "heise.de", "trace_text": DATA["trace_text"],
               "argv": ["tcp-paris", "heise.de"], "source": "paths", "origin_how": "ip"}
    write_export("pdf", str(tmp_path / "r.pdf"), current)
    doc = QPdfDocument()
    doc.load(str(tmp_path / "r.pdf"))
    words = " ".join(" ".join(doc.getAllText(i).text() for i in range(doc.pageCount())).split())
    assert "inferred from neighbours" in words
    write_export("json", str(tmp_path / "r.json"), current)
    body = json.loads((tmp_path / "r.json").read_text())
    hop = next(h for h in body["route"]["hops"] if h.get("address") == ADDR)
    assert hop["source"] == "neighbours" and hop["reason"].startswith("inferred from neighbours")
