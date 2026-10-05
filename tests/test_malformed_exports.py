"""A malformed export never raises: it opens, or it ends in a clear error
dialog, and nothing raises inside a Qt callback afterwards (validation round,
4c). Over the class: every number in a hop and a candidate set past any real
value (huge integers, huge floats, both signs, NaN and Infinity, which Python's
json accepts), a latitude or a longitude on its own, and JSON nested deeper
than the parser's recursion limit, in an opened file, a compared file, the
history file and the CLI's --compare."""
import copy
import json
import os
import pathlib
import sys

import pytest


from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from routemap import cli, config, imported, service  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent
ROUTE = json.loads((ROOT / "fixtures" / "gui" / "heise_route.json").read_text())["route"]
HOP_NUMBERS = ["hop", "min_rtt_ms", "avg_rtt_ms", "sent", "lost", "loss_pct", "distance_km", "rtt_budget_km",
               "asn", "lat", "lon"]
HUGE = [10**400, -10**400, 10**20, 1e300, -1e300]
DEEP = '{"route": ' + "[" * 200_000 + "]" * 200_000 + "}"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _export(route) -> str:
    return service.export_json(route, target="heise.de", trace_text="", argv=None, source="file", origin_how=None)


def _cases():
    for field in HOP_NUMBERS:
        for value in HUGE:
            r = copy.deepcopy(ROUTE)
            r["hops"][2][field] = value
            yield f"hop.{field}={'big' if value > 0 else '-big'}{type(value).__name__}", _export(r)
    for field in ("distance_km", "rtt_budget_km", "lat"):
        r = copy.deepcopy(ROUTE)
        cand = next(h for h in r["hops"] if h.get("candidates"))["candidates"][0] \
            if any(h.get("candidates") for h in r["hops"]) else None
        if cand is not None:
            cand[field] = 10**400
            yield f"candidate.{field}=big", _export(r)
    for token in ("NaN", "Infinity", "-Infinity"):
        text = _export(ROUTE).replace('"min_rtt_ms": ', f'"min_rtt_ms": {token}, "x": ', 1)
        yield f"min_rtt_ms={token}", text
    for keep in ("lat", "lon"):
        for how in ("null", "missing"):
            r = copy.deepcopy(ROUTE)
            hop = next(h for h in r["hops"] if h.get("lat") is not None)
            other = "lon" if keep == "lat" else "lat"
            if how == "null":
                hop[other] = None
            else:
                del hop[other]
            yield f"{keep} without {other} ({how})", _export(r)
    yield "deep nesting", DEEP


CASES = list(_cases())


def _window():
    from routemap.gui.app import Controller
    from routemap.gui.mainwindow import MainWindow
    w = MainWindow()
    c = Controller(w, config.Settings(online_lookups=False, city_db_declined=True))
    shown = []
    c.error = lambda title, message: shown.append(message)
    return w, c, shown


def _exercise(app, w, c):
    """Everything a person does next: draw, sort, select every hop."""
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w.grab()
    if c.current:
        c.refresh_panels()
        for hop in c.current["route"]["hops"]:
            c._hops_selected([hop])
        from PySide6.QtCore import Qt
        for col in range(w.table.proxy.columnCount()):
            w.table.sortByColumn(col, Qt.AscendingOrder)
        app.processEvents()
        w.grab()


@pytest.fixture
def raised(monkeypatch):
    """Exceptions inside Qt callbacks reach sys.excepthook, not the caller."""
    seen = []
    monkeypatch.setattr(sys, "excepthook", lambda t, v, tb: seen.append(f"{t.__name__}: {v}"[:120]))
    return seen


@pytest.mark.parametrize("name,text", CASES, ids=[n for n, _ in CASES])
def test_opening_a_malformed_export_ends_in_a_route_or_a_clear_error(app, tmp_path, raised, name, text):
    path = tmp_path / "export.json"
    path.write_text(text)
    w, c, shown = _window()
    c.open_path(str(path))
    _exercise(app, w, c)
    w.close()
    assert not raised, raised
    assert shown, "a file Route Map never writes must be refused with a reason"
    assert c.current is None and "export" in shown[0].lower()


@pytest.mark.parametrize("name,text", CASES, ids=[n for n, _ in CASES])
def test_comparing_with_a_malformed_export_ends_in_a_clear_error(app, tmp_path, raised, monkeypatch, name, text):
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(_export(ROUTE))
    bad.write_text(text)
    w, c, shown = _window()
    c.open_path(str(good))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(bad), "")))
    c.compare_with_file()
    _exercise(app, w, c)
    w.close()
    assert not raised, raised
    assert shown and c.current is not None


def test_a_deeply_nested_history_file_is_ignored_not_fatal():
    config.history_path().parent.mkdir(parents=True, exist_ok=True)
    config.history_path().write_text("[" * 200_000 + "]" * 200_000)
    assert config.load_history() == []


CLI_CASES = [c for c in CASES if c[0] in ("deep nesting", "hop.min_rtt_ms=bigint")]


@pytest.mark.parametrize("name,text", CLI_CASES, ids=[n for n, _ in CLI_CASES])
def test_the_cli_compare_refuses_with_a_message(tmp_path, name, text):
    bad = tmp_path / "bad.json"
    bad.write_text(text)
    trace = ROOT / "fixtures" / "routemap" / "heise_traceroute.txt"
    with pytest.raises(SystemExit, match="not a route export"):
        cli.main(["parse", str(trace), "--offline", "--origin", "Manila, PH", "--compare", str(bad)])
