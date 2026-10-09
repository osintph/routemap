"""Rate-limited loss is not reported as loss: summary, JSON, table, PDF agree.

Run over every recorded route in the GUI fixtures plus a synthetic one, so the
rule holds for the class of trace, not one example: the summary and the JSON
carry exactly the engine's verdict, and the only greyed loss cells are the
hops the engine marked as ICMP rate limiting.
"""
import json
import pathlib

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from routemap_engine import geo  # noqa: E402

from routemap import insight, service  # noqa: E402
from routemap.gui import hoptable  # noqa: E402

GUI = pathlib.Path(__file__).resolve().parent / "fixtures" / "gui"


def _synthetic():
    hops = [{"hop": n, "addresses": [f"192.0.2.{n}"], "address": f"192.0.2.{n}", "loss_pct": loss,
             "min_rtt_ms": 5.0 * n, "annotations": [], "lat": 14.6, "lon": 121.0}
            for n, loss in ((1, 0.0), (2, 40.0), (3, 20.0), (4, 0.0))]
    return {"parser": "traceroute", "parser_label": "traceroute", "target": "x", "warnings": [],
            "hoiho_ruleset_date": None, "origin": {}, "hops": geo.annotate(hops)}


ROUTES = [("synthetic", _synthetic())] + [
    (p.stem, json.loads(p.read_text())["route"]) for p in sorted(GUI.glob("*.json"))
    if "route" in json.loads(p.read_text())]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("name,route", ROUTES, ids=[n for n, _ in ROUTES])
def test_summary_and_json_carry_the_engines_verdict(name, route):
    verdict = geo.loss_verdict(route["hops"])
    assert insight.summary(route, None)["loss"] == verdict
    doc = json.loads(service.export_json(route, target="x", trace_text="", argv=None,
                                         source="test", origin_how=None))
    assert doc["loss"] == verdict


@pytest.mark.parametrize("name,route", ROUTES, ids=[n for n, _ in ROUTES])
def test_only_rate_limited_loss_is_greyed(app, name, route):
    model = hoptable.HopModel()
    model.set_hops(route["hops"], {})
    col = hoptable.KEYS.index("loss")
    for row, hop in enumerate(model.hops):
        if hop.get("lat") is None:
            continue   # unplaced rows are greyed whole, for another reason
        fg = model.data(model.index(row, col), Qt.ForegroundRole)
        assert (fg is not None) is (geo.ANNOT_ICMP_LIMIT in (hop.get("annotations") or [])), hop["hop"]


def test_the_synthetic_route_names_its_rate_limited_hops():
    v = insight.summary(_synthetic(), None)["loss"]
    assert v["rate_limited"] == [2, 3] and v["loss_pct"] == 0.0
    assert v["text"].startswith("No loss to the destination.")
