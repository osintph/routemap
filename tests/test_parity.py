"""Platform parity: one recorded trace, rendered, must have the same structure
on Windows, macOS and Linux (panels, legends, chart series, table columns,
map items, style, font). CI runs this on all three; the reference is
tests/fixtures/parity/expected.json (regenerate with ROUTEMAP_UPDATE_PARITY=1
after an intended change, and review the diff).

No network: the RIPEstat and Atlas answers are the recorded ones in
tests/fixtures/ripe."""
import asyncio
import json
import os
import pathlib

import httpx
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
EXPECTED = HERE / "fixtures" / "parity" / "expected.json"


def _insight(route):
    from routemap import config, insight
    from routemap_engine import baseline, ripe
    stat_rec = json.loads((HERE / "fixtures" / "ripe" / "ripestat.json").read_text())
    atlas_rec = json.loads((HERE / "fixtures" / "ripe" / "atlas.json").read_text())

    def stat_handler(request):
        name = request.url.path.split("/")[2]
        if name == "rpki-validation" and request.url.params["resource"] == "AS12306":
            return httpx.Response(200, json=stat_rec["rpki-validation-unknown"])
        return httpx.Response(200, json=stat_rec[name])

    def atlas_handler(request):
        path = request.url.path
        if path.endswith("/anchors/"):
            return httpx.Response(200, json=atlas_rec[f"anchors-{request.url.params['country']}"])
        if path.endswith("/latest/"):
            return httpx.Response(200, json=atlas_rec["latest"])
        return httpx.Response(200, json=atlas_rec["measurements"])

    s = config.Settings()
    ins = insight.offline(route, s)
    import datetime as dt
    end = dt.datetime.fromisoformat(stat_rec["bgp-updates"]["data"]["end"])
    asyncio.run(insight.online(route, ins, s, user_agent="t", sourceapp="t", now=end,
                               stat=ripe.RipeStat(user_agent="t", sourceapp="t",
                                                  transport=httpx.MockTransport(stat_handler)),
                               atlas=baseline.Baseline(user_agent="t", transport=httpx.MockTransport(atlas_handler))))
    return ins


def test_the_rendered_structure_is_the_same_on_every_platform():
    from routemap.gui import parity, theme
    from routemap.gui.mainwindow import MainWindow
    app = QApplication.instance() or QApplication([])
    theme.apply(app, "light")
    route = json.loads((HERE / "fixtures" / "gui" / "heise_ecmp_route.json").read_text())["route"]
    ins = _insight(route)
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    window.show_result(route, "heise.de", ["icmp", "-m", "30", "-q", "3", "-w", "1", "heise.de"])
    details = ((ins.get("online") or {}).get("hops")) or {}
    window.table.set_hops(route["hops"], details)
    window.insight.show_summary(route, ins, origin_cc="PH")
    app.processEvents()
    snap = parity.snapshot(window)
    window.close()
    if os.environ.get("ROUTEMAP_UPDATE_PARITY"):
        EXPECTED.write_text(json.dumps(snap, indent=1, sort_keys=True) + "\n")
    expected = json.loads(EXPECTED.read_text())
    assert snap == expected, json.dumps({k: (snap.get(k), expected.get(k)) for k in snap
                                         if snap.get(k) != expected.get(k)}, indent=1)
