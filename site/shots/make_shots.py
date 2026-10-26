"""
The site's screenshots, rendered by the app's own code from saved, sanitized
traces (tests/fixtures/gui/; the first hops are documentation addresses), never
from a live trace.

    QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2 python site/shots/make_shots.py [OUT]

Writes NAME-light.EXT and NAME-dark.EXT into site/assets/img/ (or OUT): the
window views at 1600 x 1000 (rendered at twice that and scaled down), the crops
at twice their size on screen. The origin is "Manila, PH", set in Settings.
The Windows-native image is not made here: it comes from the mockup workflow's
Windows runner (.github/workflows/mockup.yml), which renders the same fixture.
The PDF page needs poppler's pdftoppm.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRect, QSize, Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from routemap_engine import diff as route_diff  # noqa: E402

from routemap import config, insight  # noqa: E402
from routemap.gui import mapview, mockup, report, theme  # noqa: E402

ORIGIN = (14.6, 121.0, "Manila, PH")
SIZE = QSize(1600, 1000)
FIX = ROOT / "tests" / "fixtures" / "gui"


def fixture(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def scheme(app, dark: bool) -> None:
    mockup.set_scheme(dark)
    theme.apply(app, "dark" if dark else "light")


def summary(route: dict) -> dict:
    ins = insight.offline(route, config.Settings(online_lookups=False))
    # Rendered offline, and it says so: no RIPEstat or Atlas data is invented.
    ins["online"] = {"status": insight.OFF}
    return ins


def window(route: dict, target: str, argv: list[str], trace_text: str, **kw):
    w = mockup.MainWindow()
    w.resize(SIZE)
    w.set_origin_status(ORIGIN[2], "city")
    w.set_tool_status(argv)
    w.show()
    w.show_result(route, target, argv, trace_text=trace_text, **kw)
    w.history_dock.hide()
    w.insight.show_summary(route, summary(route))
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


def main(argv: list[str]) -> int:
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
        w.table.set_hops(new["hops"], {}, change["new_marks"], None)
        w.insight.show_summary(new, summary(new), diff=change, diff_label="the earlier run")
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
