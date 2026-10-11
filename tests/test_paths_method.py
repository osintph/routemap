"""D3: the probe method of a path discovery, TCP or ICMP, is shown wherever
the paths are: the window, the CLI text, the PDF, the PNG and the JSON."""
import json

import pytest

from routemap import cli, service

from routemap_engine import analyse_paths, multipath
from routemap_engine.geo import Sources

from test_paths_gui import DST, PLACES, Lab, app  # noqa: F401


@pytest.fixture(scope="module")
def _paths_route():
    import asyncio
    lab = Lab()
    d = multipath.Discoverer("heise.de", DST, lab, clock=lab.clock).run()

    async def ip_db(addresses):
        return {a: {"lat": PLACES[a][0], "lon": PLACES[a][1], "city": f"City{a[-1]}", "cc": "DE"}
                for a in addresses if a in PLACES}
    return asyncio.run(analyse_paths(d, (14.6, 121.0), sources=Sources(hoiho=None, ip_db=ip_db, ptr=None)))


def _with_method(route, method, af=4):
    d = route.to_dict() if hasattr(route, "to_dict") else dict(route)
    d["paths"] = dict(d["paths"], method=method, af=af)
    if method == "tcp-paris":
        d["paths"]["port"] = 443
    else:
        d["paths"].pop("port", None)
    return d


@pytest.mark.parametrize("method,af,label", [("tcp-paris", 4, "TCP port 443"), ("icmp-paris", 4, "ICMP"),
                                             ("icmp-paris", 6, "ICMPv6"), ("tcp-paris", 6, "TCP port 443")])
def test_the_label(method, af, label):
    disc = {"method": method, "af": af, **({"port": 443} if method == "tcp-paris" else {})}
    assert service.paths_method(disc) == label


def test_the_cli_text_says_the_method(_paths_route):
    assert cli._paths_text(_with_method(_paths_route, "tcp-paris")).startswith("Built-in Paris, TCP port 443 ·")
    assert cli._paths_text(_with_method(_paths_route, "icmp-paris")).startswith("Built-in Paris, ICMP ·")


def test_the_window_says_the_method(app, _paths_route):
    from routemap.gui.panels import PathsPanel
    panel = PathsPanel()
    route = _with_method(_paths_route, "tcp-paris")
    panel.set_paths(route["paths"], route["hops"])
    assert panel.toggle.text().endswith("· TCP port 443")
    assert "Probes: TCP port 443." in panel.note.text() and "spread TCP probes" in panel.note.text()
    route = _with_method(_paths_route, "icmp-paris")
    panel.set_paths(route["paths"], route["hops"])
    assert panel.toggle.text().endswith("· ICMP") and "spread ICMP probes" in panel.note.text()


def test_pdf_png_and_json_say_the_method(app, tmp_path, _paths_route, monkeypatch):
    from routemap import config
    from routemap.gui import app as gui_app
    from routemap.gui import mapview
    route = _with_method(_paths_route, "tcp-paris")
    current = {"route": route, "target": "heise.de", "source": "paths", "trace_text": "", "argv": ["tcp-paris"]}
    settings = config.Settings(online_lookups=False)
    titles = []
    real = mapview.render_png
    monkeypatch.setattr(mapview, "render_png", lambda *a, **k: (titles.append(k.get("title")), real(*a, **k))[1])
    gui_app.write_export("png", str(tmp_path / "m.png"), current, settings=settings)
    assert titles[-1].endswith("· paths by TCP port 443")
    gui_app.write_export("json", str(tmp_path / "m.json"), current, settings=settings)
    paths = json.loads((tmp_path / "m.json").read_text())["route"]["paths"]
    assert paths["method"] == "tcp-paris" and paths["port"] == 443
    gui_app.write_export("pdf", str(tmp_path / "m.pdf"), current, settings=settings)
    from PySide6.QtPdf import QPdfDocument
    doc = QPdfDocument()
    doc.load(str(tmp_path / "m.pdf"))
    flat = " ".join(doc.getAllText(i).text() for i in range(doc.pageCount())).replace("\n", " ")
    assert "Paths: at least 2 · TCP port 443" in flat and "do not spread TCP probes" in flat
    assert "ICMP" not in flat.split("Paths: at least")[1].split("How locations")[0]
    assert "built-in Paris prober (TCP port 443)" in flat


def test_the_summary_line_says_the_method(app, _paths_route):
    from routemap.gui.mainwindow import MainWindow
    w = MainWindow()
    route = _with_method(_paths_route, "tcp-paris")
    route["parser_label"] = "Built-in TCP prober (port 443)"
    w.show_result(route, "heise.de", ["tcp-paris", "heise.de"])
    text = w.summary.text()
    assert "Paris, TCP port 443" in text and "Built-in TCP prober (port 443)" in text and "ICMP" not in text
    w.close()
