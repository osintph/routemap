"""
The site's screenshots, rendered by the app's own code from saved, sanitized
traces (tests/fixtures/gui/; the first hops are documentation addresses), never
from a live trace.

    QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2 python site/shots/make_shots.py [OUT]
    python site/shots/make_shots.py --record      # once: fetch the online details

The route summary shows real public data: RIPEstat (prefixes, RPKI, the RIS
view, BGP updates) and RIPE Atlas (the typical latency) for the saved traces'
public hops, fetched once with --record into tests/fixtures/gui/heise_online.json
and rendered from that file with the clock set to the fetch time and no network
at all, so the images can be made again and come out the same. The first hops
are documentation addresses, which the app never looks up.

Writes NAME-light.EXT and NAME-dark.EXT into site/assets/img/ (or OUT): the
window views at 1600 x 1000 (rendered at twice that and scaled down), the crops
at twice their size on screen. The origin is "Manila, PH", set in Settings.
The Windows-native image is made on the mockup workflow's Windows runner
(.github/workflows/mockup.yml) with --windows OUT: the window view, light, at
the runner's own scale, from the same saved trace and online details.
The PDF page needs poppler's pdftoppm.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRect, QSize, Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from routemap_engine import diff as route_diff  # noqa: E402

import httpx  # noqa: E402
from routemap_engine import baseline, ripe  # noqa: E402

from routemap import config, insight, service  # noqa: E402
from routemap.gui import mapview, mockup, report, theme  # noqa: E402

ORIGIN = (14.6, 121.0, "Manila, PH")
SIZE = QSize(1600, 1000)
FIX = ROOT / "tests" / "fixtures" / "gui"
ONLINE = FIX / "heise_online.json"
# The routes whose route summary shows online details.
ONLINE_ROUTES = ("heise_ecmp_route", "agent_route", "amazon_route")


class JsonCache:
    """The engine's Cache protocol over a dict, saved as JSON (the clients'
    own cache keys and entries, untouched)."""

    def __init__(self, entries: dict | None = None):
        self.entries = dict(entries or {})

    def get(self, key):
        return self.entries.get(key)

    def set(self, key, value):
        self.entries[key] = value


class Offline(httpx.AsyncBaseTransport):
    """No network while rendering: an answer missing from the fixture fails."""

    async def handle_async_request(self, request):
        raise httpx.ConnectError(f"not in {ONLINE.name}: {request.url}")


def online_details(route: dict, cache: JsonCache, when: _dt.datetime, transport=None) -> dict:
    """insight.online for *route*, its clients on *cache*, at *when*."""
    settings = config.Settings(online_lookups=True)
    ins = insight.offline(route, settings)
    clock = when.timestamp
    stat = ripe.RipeStat(user_agent=service.user_agent(), sourceapp=service.SOURCEAPP, cache=cache,
                         transport=transport, now=(clock if transport else time.time))
    atlas = baseline.Baseline(user_agent=service.user_agent(), cache=cache, transport=transport,
                              now=(clock if transport else time.time))
    asyncio.run(insight.online(route, ins, settings, user_agent=service.user_agent(),
                               sourceapp=service.SOURCEAPP, now=when, stat=stat, atlas=atlas))
    return ins


def record() -> int:
    """Fetch the online details once and keep every answer in the fixture."""
    cache, when = JsonCache(), _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    for name in ONLINE_ROUTES:
        ins = online_details(with_origin(fixture(name)["route"]), cache, when)
        status = ins["online"]["status"]
        print(name, status, ins["online"].get("errors") or "")
        if status != "done":
            raise SystemExit(f"{name}: online details {status}; nothing written")
    ONLINE.write_text(json.dumps({
        "_note": "RIPEstat and RIPE Atlas answers for the public hops of heise_ecmp_route.json, "
                 "agent_route.json and amazon_route.json, as the app's own clients fetched and cached them (site/shots/"
                 "make_shots.py --record). The first hops are documentation addresses and were not "
                 "looked up. Public routing data, not about the tester.",
        "fetched_at": when.isoformat(), "entries": cache.entries}, indent=1, sort_keys=True), encoding="utf-8")
    print(f"{len(cache.entries)} answers written to {ONLINE}")
    return 0


def summary(route: dict) -> dict:
    """The route summary from the fixture's answers, or offline if the route has none."""
    data = json.loads(ONLINE.read_text(encoding="utf-8"))
    when = _dt.datetime.fromisoformat(data["fetched_at"])
    ins = online_details(route, JsonCache(data["entries"]), when, transport=Offline())
    if ins["online"]["status"] != "done" or ins["online"].get("errors"):
        raise SystemExit(f"online details {ins['online']['status']}: {ins['online'].get('errors')}; "
                         "run --record again")
    return ins


def data_date() -> str:
    when = _dt.datetime.fromisoformat(json.loads(ONLINE.read_text(encoding="utf-8"))["fetched_at"])
    return when.strftime("%-d %b %Y")


def fixture(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def scheme(app, dark: bool) -> None:
    mockup.set_scheme(dark)
    theme.apply(app, "dark" if dark else "light")


def window(route: dict, target: str, argv: list[str], trace_text: str, **kw):
    w = mockup.MainWindow()
    w.resize(SIZE)
    w.set_origin_status(ORIGIN[2], "city")
    w.set_tool_status(argv)
    w.show()
    w.show_result(route, target, argv, trace_text=trace_text, **kw)
    w.history_dock.hide()
    ins = summary(route)
    w.insight.show_summary(route, ins, origin_cc="PH")
    w.table.set_hops(route.get("hops") or [], ins["online"].get("hops") or {}, None, None)
    w.table.setFocus()
    mockup._settle(w)
    w.map.fit_route()
    mockup._settle(w, 10)
    return w


def with_origin(route: dict) -> dict:
    return dict(route, origin=dict(route.get("origin") or {}, label=ORIGIN[2]))


def grab(widget, rect: QRect | None = None) -> QImage:
    pixmap = widget.grab(rect) if rect is not None else widget.grab()
    return pixmap.toImage()


def save_full(image: QImage, path: pathlib.Path) -> None:
    """A window view at 1600 x 1000, from the 2x render."""
    image.scaled(SIZE, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(str(path), quality=88)


def area(w, child) -> QRect:
    """*child*'s rectangle in *w*'s coordinates."""
    top_left = child.mapTo(w, child.rect().topLeft())
    return QRect(top_left, child.size())


def windows(out: pathlib.Path) -> int:
    """The Windows-native window view (run on Windows, no scale factor)."""
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    mockup.MANILA = ORIGIN
    scheme(app, False)
    heise = fixture("heise_ecmp_route")
    w = window(with_origin(heise["route"]), "heise.de", mockup._argv("heise.de"), heise["trace_text"])
    w.resize(QSize(1280, 800))
    mockup._settle(w, 6)
    w.map.fit_route()
    mockup._settle(w, 10)
    grab(w).save(str(out / "windows-light.png"))
    w.close()
    print(f"written {out / 'windows-light.png'}")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--record"]:
        return record()
    if argv[:1] == ["--windows"]:
        return windows(pathlib.Path(argv[1]))
    out = pathlib.Path(argv[0]) if argv else ROOT / "site" / "assets" / "img"
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    mockup.MANILA = ORIGIN
    heise = fixture("heise_ecmp_route")
    probes = fixture("heise_probes")
    amazon = fixture("amazon_route")
    agent = fixture("agent_route")
    argv_heise = mockup._argv("heise.de")
    written = []
    for dark in (False, True):
        scheme(app, dark)
        suffix = "-dark" if dark else "-light"

        w = window(with_origin(heise["route"]), "heise.de", argv_heise, heise["trace_text"])
        save_full(grab(w), out / f"window{suffix}.jpg")
        save_full(grab(w), out / f"explainer{suffix}.jpg")
        grab(w, area(w, w.statusBar())).save(str(out / f"statusbar{suffix}.png"))
        table = w.table
        grab(w, area(w, table)).save(str(out / f"rule1-sources{suffix}.png"))
        w.map.set_projection("globe")
        mockup._settle(w, 12)
        save_full(grab(w), out / f"globe{suffix}.jpg")
        w.close()

        route = dict(with_origin(heise["route"]), resolved=probes["resolved"], dns=probes["dns"],
                     ports=probes["ports"])
        w = window(route, "heise.de", argv_heise, heise["trace_text"])
        w.resize(QSize(1600, 1300))          # room for all six ports without a scroll bar
        w.dns_panel.expand(True)
        w.ports_panel.expand(True)
        mockup._settle(w, 8)
        top = area(w, w.dns_panel).united(area(w, w.ports_panel))
        grab(w, top).save(str(out / f"probes{suffix}.png"))
        w.close()

        w = window(with_origin(amazon["route"]), "amazon.com", mockup._argv("amazon.com"), amazon["trace_text"],
                   expand_unplaced=True)
        grab(w, area(w, w.unplaced)).save(str(out / f"rule3-unplaced{suffix}.png"))
        w.close()

        w = window(agent["route"], "heise.de", ["ssh fra-vps", "icmp", "heise.de"], agent["trace_text"],
                   agent="fra-vps")
        w.set_agents([a["name"] for a in mockup.AGENT_SETTINGS], "fra-vps")
        w.set_origin_status("fra-vps, Frankfurt am Main, DE", "agent-city")
        mockup._settle(w, 8)
        save_full(grab(w), out / f"agent{suffix}.jpg")
        w.close()

        card = mockup._tooltip_card(with_origin(heise["route"]), 8)
        card.setWordWrap(False)
        card.adjustSize()
        card.show()
        mockup._settle(card)
        card.resize(card.sizeHint())
        mockup._settle(card)
        grab(card).save(str(out / f"rule2-rejected{suffix}.png"))
        card.close()

        # Two saved runs to heise.de: hop 8 was Marseille in one and Singapore in the other.
        old = with_origin(fixture("heise_route")["route"])
        new = with_origin(heise["route"])
        w = window(new, "heise.de", argv_heise, heise["trace_text"])
        change = route_diff.diff_routes(old, new)
        w.map.set_comparison(old, change["new_marks"])
        ins = summary(new)
        w.insight.show_summary(new, ins, origin_cc="PH", diff=change, diff_label="the earlier run")
        w.table.set_hops(new["hops"], ins["online"].get("hops") or {}, change["new_marks"], None)
        mockup._settle(w, 6)
        w.map.fit_route()
        mockup._settle(w, 10)
        save_full(grab(w), out / f"compare{suffix}.jpg")
        w.close()

        if not dark:
            pdf = out / "report.pdf"
            # The date the saved trace was made (the mockup's history says 3 Oct 13:05).
            when = _dt.datetime(2026, 10, 3, 13, 5, tzinfo=_dt.timezone(_dt.timedelta(hours=8)))
            report.write_pdf(str(pdf), with_origin(heise["route"]), target="heise.de",
                             trace_text=heise["trace_text"], tool_label="traceroute -m 30 -q 3 -w 1",
                             origin_how="city", source="local", when=when, insight=summary(heise["route"]))
            # Poppler, as a PDF viewer draws it (Qt's own PDF renderer misses the embedded fonts).
            subprocess.run(["pdftoppm", "-jpeg", "-jpegopt", "quality=90", "-f", "1", "-l", "1",
                            "-scale-to-x", "1240", "-scale-to-y", "1754", "-singlefile", str(pdf),
                            str(out / "pdf-page1")], check=True)
            pdf.unlink()

        image = mapview.render_png(with_origin(heise["route"]), title="heise.de from Manila", dark=dark,
                                   provenance=f"{mockup.DISPLAY_NAME} {mockup.VERSION} · a saved trace · "
                                              "traceroute -m 30 -q 3 -w 1 · "
                                              f"{mockup.geometry.ATTRIBUTION} · GeoNames CC BY 4.0",
                                   destination="heise.de")
        image.save(str(out / f"export{suffix}.jpg"), quality=88)
        written += [suffix]
    print(f"site images written to {out} ({', '.join(written)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
