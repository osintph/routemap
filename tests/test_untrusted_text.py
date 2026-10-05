"""Text from files and from other people's services is shown as text, never
interpreted (RM-01, hardening 2 and 3), over the class: every free-text field
of a route, of the RIPEstat and Atlas answers, of an export and of a history
entry carries markup, and no widget that interprets markup receives it raw."""
import asyncio
import copy
import json
import os
import pathlib

import httpx
import pytest


from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import Qt as QtGui_Qt  # noqa: E402
from PySide6.QtWidgets import QAbstractItemView, QApplication, QGraphicsView, QLabel, QTextEdit  # noqa: E402

from routemap import config, insight, service  # noqa: E402
from routemap_engine import analyse_sync, baseline, geo, ripe  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent
MARK = '<img src="http://127.0.0.1:9/m.png"><a href="file:///m">x</a>'
RAW = ('src="http://127.0.0.1:9', 'href="file:///m"')
# Values the code looks up or compares; markup there is a different failure (an
# unknown key), handled by the import checks, not by escaping.
STRUCTURAL = {"source", "state", "rpki", "provider", "precision", "parser", "annotations", "kind",
              "asn_source", "ip_provider", "status", "prefix", "resource", "rir", "country", "cc"}


def poison(value, key=None):
    if isinstance(value, dict):
        return {k: poison(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [poison(v, key) for v in value]
    if isinstance(value, str) and key not in STRUCTURAL and not value.replace(".", "").isdigit():
        return value + MARK
    return value


def interpreted_markup(root) -> list[str]:
    """Raw markup from the data in any place Qt would render it as rich text."""
    found = []

    def check(where, text, rich):
        if rich and any(r in text for r in RAW):
            found.append(f"{where}: {text[:120]!r}")

    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QWidget
    for w in [root, *root.findChildren(QWidget)]:
        name = f"{type(w).__name__}({w.objectName() or ''})"
        if isinstance(w, QLabel):
            if w.openExternalLinks() and w.window() is root:
                found.append(f"{name}: opens external links in the main window")
            fmt = w.textFormat()
            rich = fmt == Qt.RichText or (fmt == Qt.AutoText and QtGui_Qt.mightBeRichText(w.text()))
            check(name, w.text(), rich)
        if isinstance(w, QTextEdit):
            check(name, w.toHtml(), True)
        tip = w.toolTip()
        check(name + ".toolTip", tip, QtGui_Qt.mightBeRichText(tip))
        if isinstance(w, QGraphicsView) and w.scene() is not None:
            for item in w.scene().items():
                tip = item.toolTip()
                check(f"{name} scene {type(item).__name__}.toolTip", tip, QtGui_Qt.mightBeRichText(tip))
        if isinstance(w, QAbstractItemView) and w.model() is not None:
            m = w.model()
            try:
                cols = m.columnCount(QModelIndex())
            except TypeError:        # list models keep it private: one column
                cols = 1
            for r in range(min(m.rowCount(QModelIndex()), 300)):
                for c in range(max(1, cols)):
                    tip = m.data(m.index(r, c), Qt.ToolTipRole)
                    if isinstance(tip, str):
                        check(f"{name}[{r},{c}].toolTip", tip, QtGui_Qt.mightBeRichText(tip))
    return found


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTEMAP_CONFIG_DIR", str(tmp_path / "config"))
    insight._ASN = None
    yield
    insight._ASN = None


def _poisoned_insight_and_route():
    root = ROOT / "fixtures" / "ripe"
    stat_rec = poison(json.loads((root / "ripestat.json").read_text()))
    atlas_rec = poison(json.loads((root / "atlas.json").read_text()))
    clean_atlas = json.loads((root / "atlas.json").read_text())

    def stat_handler(request):
        name = request.url.path.split("/")[2]
        key = ("rpki-validation-unknown" if name == "rpki-validation"
               and request.url.params["resource"] == "AS12306" else name)
        return httpx.Response(200, json=stat_rec[key])

    def atlas_handler(request):
        path = request.url.path
        if path.endswith("/anchors/"):
            return httpx.Response(200, json=atlas_rec[f"anchors-{request.url.params['country']}"])
        if path.endswith("/latest/"):
            return httpx.Response(200, json=atlas_rec["latest"])
        return httpx.Response(200, json=atlas_rec["measurements"])

    sample = (ROOT.parent / "routemap" / "gui" / "data" / "sample_trace.txt").read_text()
    route = analyse_sync(sample, (14.5995, 120.9842), sources=geo.Sources(ip_db=None)).to_dict()
    lat, lon = clean_atlas["expect"]["dest_coords"]
    route["hops"][-1].update(lat=lat, lon=lon, cc="DE", source="ip-db", place="Frankfurt, DE")
    s = config.Settings()
    ins = insight.offline(route, s)
    stat = ripe.RipeStat(user_agent="t", sourceapp=service.SOURCEAPP, transport=httpx.MockTransport(stat_handler))
    atlas = baseline.Baseline(user_agent="t", transport=httpx.MockTransport(atlas_handler))
    asyncio.run(insight.online(route, ins, s, user_agent="t", sourceapp=service.SOURCEAPP, stat=stat, atlas=atlas))
    return poison(route), poison(ins)


def _window(settings=None):
    from routemap.gui.app import Controller
    from routemap.gui.mainwindow import MainWindow
    window = MainWindow()
    controller = Controller(window, settings or config.Settings(online_lookups=False, city_db_declined=True))
    return window, controller


def test_poisoned_answers_and_route_fields_reach_no_rich_text(app):
    route, ins = _poisoned_insight_and_route()
    window, c = _window()
    c.current = {"route": route, "target": "heise.de" + MARK, "trace_text": "", "argv": ["traceroute", MARK],
                 "source": "file", "origin_how": "coords", "when": None, "insight": ins}
    window.show_result(route, "heise.de" + MARK, ["traceroute", MARK])
    c.refresh_panels()
    for hop in route["hops"]:
        c._hops_selected([hop])
    app.processEvents()
    problems = interpreted_markup(window)
    window.close()
    assert not problems, "\n".join(problems[:15])


def test_a_hostile_export_is_rebuilt_before_it_is_shown(app, tmp_path):
    route, ins = _poisoned_insight_and_route()
    doc = json.loads(service.export_json(route, target="heise.de" + MARK, trace_text="x" + MARK,
                                          argv=["traceroute", MARK], source="file", origin_how="coords",
                                          insight=ins))
    doc["route"]["parser_label"] = MARK
    doc["route"]["warnings"] = [MARK]
    doc["route"]["hoiho_ruleset_date"] = MARK
    for hop in doc["route"]["hops"]:
        hop.update(hop="7" + MARK if hop["hop"] == 1 else hop["hop"], asn=MARK, cc=MARK)
    doc["insight"]["as_path"] = [{"asn": MARK, "name": MARK, "rpki": MARK}]
    path = tmp_path / "export.json"
    path.write_text(json.dumps(doc))
    window, c = _window()
    c.open_path(str(path))
    c.refresh_panels()
    for hop in (c.current or {}).get("route", {}).get("hops", []):
        c._hops_selected([hop])
    app.processEvents()
    problems = interpreted_markup(window)
    shown = (c.current or {}).get("insight") or {}
    window.close()
    assert c.current is not None, "a well-formed export with hostile text still opens"
    assert not problems, "\n".join(problems[:15])
    assert MARK not in json.dumps(shown), "the saved insight is recomputed, not trusted"


def test_an_oversized_file_is_refused_before_it_is_read(app, tmp_path):
    from routemap import imported
    big = tmp_path / "big.json"
    big.write_bytes(b"{" + b" " * (imported.MAX_FILE_BYTES + 10) + b"}")
    with pytest.raises(imported.ImportRejected):
        imported.read_file(str(big))


def test_history_entries_are_rebuilt_when_read(app, tmp_path):
    route, _ins = _poisoned_insight_and_route()
    entry = {"route": route, "target": "heise.de" + MARK, "when": MARK, "hops": MARK, "placed": 3,
             "tool": MARK, "argv": [MARK], "trace_text": MARK, "source": MARK}
    good = dict(entry, when=1759600000.0, hops=16)
    config.history_path().parent.mkdir(parents=True, exist_ok=True)
    config.history_path().write_text(json.dumps([entry, good, "junk", {"route": "x"}]))
    entries = config.load_history()
    assert len(entries) == 1 and isinstance(entries[0]["when"], float)
    window, c = _window(config.Settings(online_lookups=False, city_db_declined=True, history_enabled=True))
    c.history = entries
    window.history.set_entries(entries)
    c.open_history(0)
    app.processEvents()
    problems = interpreted_markup(window)
    window.close()
    assert not problems, "\n".join(problems[:15])


def test_numbers_and_codes_given_as_markup_are_escaped_too(app):
    """ASN and country code given as markup, bypassing the import checks: the
    sinks escape them as well (defence in depth). The hop number stays a number:
    a non-numeric hop is type confusion, which the import stops at the door."""
    route, ins = _poisoned_insight_and_route()
    for hop in route["hops"]:
        hop.update(cc=MARK, asn=MARK)
    for step in ins.get("as_path") or []:
        step["asn"] = MARK
    window, c = _window()
    c.current = {"route": route, "target": "heise.de", "trace_text": "", "argv": None,
                 "source": "file", "origin_how": "coords", "when": None, "insight": ins}
    window.show_result(route, "heise.de", None)
    c.refresh_panels()
    for hop in route["hops"]:
        c._hops_selected([hop])
    app.processEvents()
    problems = interpreted_markup(window)
    window.close()
    assert not problems, "\n".join(problems[:15])


@pytest.mark.parametrize("name", ["heise_route", "heise_ecmp_route", "amazon_route"])
def test_a_real_route_survives_the_rebuild_unchanged(name):
    from routemap import imported
    route = json.loads((ROOT / "fixtures" / "gui" / f"{name}.json").read_text())["route"]
    assert imported.route(copy.deepcopy(route)) == route


def test_the_origin_place_and_the_live_trace_state_are_text(app):
    """The origin's place name comes from the public-IP lookup or Settings; the
    live state names the target and the tool's progress note."""
    window, c = _window()
    window.set_origin_status("Manila" + MARK, "ip")
    route, _ins = _poisoned_insight_and_route()
    window.show_tracing("heise.de" + MARK, ["traceroute", MARK], hop_note=MARK)
    window.update_live(route, "heise.de" + MARK, hop_note=MARK)
    app.processEvents()
    problems = interpreted_markup(window)
    window.close()
    assert not problems, "\n".join(problems[:15])


def test_no_label_in_the_main_window_guesses_its_format(app):
    """Qt.AutoText decides from the content, so data could switch a label to
    rich text. Every label says PlainText, or RichText built with escaping."""
    route, ins = _poisoned_insight_and_route()
    window, c = _window()
    c.current = {"route": route, "target": "heise.de", "trace_text": "", "argv": ["traceroute", "heise.de"],
                 "source": "file", "origin_how": "coords", "when": None, "insight": ins}
    window.show_result(route, "heise.de", ["traceroute", "heise.de"])
    c.refresh_panels()
    c._hops_selected([route["hops"][3]])
    app.processEvents()
    from PySide6.QtWidgets import QWidget
    guessing = [f"{type(w.parent()).__name__}: {w.text()[:40]!r}" for w in window.findChildren(QLabel)
                if w.textFormat() == Qt.AutoText]
    window.close()
    assert not guessing, guessing
