"""
The PDF report, drawn with QPdfWriter: A4, selectable text, the map as an image.

Contents, in order: title and the facts of the trace (target, date, origin and
how it was set, tool and flags, counts), the map at the full route extent with
its legend, the hop table, the unplaced hops with their reasons, a short note on
how locations were decided, and the raw trace text as an appendix.
"""
from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen

from routemap.__about__ import DISPLAY_NAME, VERSION
from routemap.gui import geometry, mapview, theme
from routemap.gui.hoptable import NOTE_SHORT, rate_limited
from routemap.insight import RPKI_SHORT
from routemap_engine.geo import loss_verdict

INK = QColor("#1f2933")
MUTED = QColor("#5f6b78")
RULE = QColor("#d3d9df")
ZEBRA = QColor("#f4f6f8")

METHOD = (
    "Each hop is placed from the router's own hostname first: CAIDA Hoiho's published "
    "naming rules, then the carrier site-code table built from each carrier's own router "
    "list. An IP geolocation database is used only when neither places the hop: DB-IP Lite "
    "City on this machine when it is installed, RIPEstat online otherwise; the Source "
    "column says which. Every candidate location is checked against the speed of light in "
    "fibre: a place further away than the hop's fastest round trip allows (about 100 km per "
    "millisecond, plus 300 km for the origin's city-level precision) is rejected, whichever "
    "source claimed it, and so is a database answer between two hops in one area when the "
    "RTT did not rise enough to pay for the detour. Private, CGNAT and reserved addresses are "
    "shown at the origin and never looked up."
)


class _Flow:
    """A cursor down the page that starts a new page when it runs out."""

    def __init__(self, writer: QPdfWriter, painter: QPainter, footer: str):
        self.writer, self.p, self.footer = writer, painter, footer
        self.dpi = writer.resolution()
        self.page_no = 1
        rect = writer.pageLayout().paintRectPixels(self.dpi)
        self.width, self.height = rect.width(), rect.height()
        self.bottom = self.height - self.mm(10)
        self.y = 0.0

    def mm(self, value: float) -> float:
        return value * self.dpi / 25.4

    def font(self, size: float, bold: bool = False, mono: bool = False) -> QFont:
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont) if mono else QFont()
        font.setPointSizeF(size)
        font.setBold(bold)
        return font

    def _footer(self):
        self.p.save()
        self.p.setFont(self.font(7.5))
        self.p.setPen(MUTED)
        self.p.drawText(QRectF(0, self.height - self.mm(6), self.width, self.mm(6)),
                        Qt.AlignLeft | Qt.AlignVCenter, self.footer)
        self.p.drawText(QRectF(0, self.height - self.mm(6), self.width, self.mm(6)),
                        Qt.AlignRight | Qt.AlignVCenter, f"Page {self.page_no}")
        self.p.restore()

    def new_page(self):
        self._footer()
        self.writer.newPage()
        self.page_no += 1
        self.y = 0.0

    def need(self, height: float):
        if self.y + height > self.bottom:
            self.new_page()

    def text(self, value: str, size: float = 9.5, bold: bool = False, color: QColor = INK,
             mono: bool = False, gap: float = 1.5, indent: float = 0.0):
        font = self.font(size, bold, mono)
        metrics = QFontMetricsF(font, self.writer)
        width = self.width - indent
        flags = int(Qt.TextWordWrap | Qt.AlignLeft)
        height = metrics.boundingRect(QRectF(0, 0, width, 1e6), flags, value).height()
        self.need(height)
        self.p.setFont(font)
        self.p.setPen(color)
        self.p.drawText(QRectF(indent, self.y, width, height), flags, value)
        self.y += height + self.mm(gap)

    def rule(self, gap: float = 2.0):
        self.need(self.mm(gap) * 2)
        self.p.setPen(QPen(RULE, self.mm(0.25)))
        self.p.drawLine(0, int(self.y), int(self.width), int(self.y))
        self.y += self.mm(gap)

    def heading(self, value: str):
        self.need(self.mm(14))
        self.y += self.mm(3)
        self.text(value, 12, bold=True, gap=2)

    def table(self, header: list[str] | None, rows: list[list[str]], widths_mm: list[float],
              size: float = 7.5, align_right: set[int] = frozenset(),
              muted: set[tuple[int, int]] = frozenset()):
        font, bold = self.font(size), self.font(size, bold=True)
        metrics = QFontMetricsF(font, self.writer)
        scale = self.width / self.mm(sum(widths_mm))
        widths = [self.mm(w) * scale for w in widths_mm]
        pad = self.mm(1.2)

        def row_height(cells, f):
            m = QFontMetricsF(f, self.writer)
            return max(m.boundingRect(QRectF(0, 0, w - 2 * pad, 1e6),
                                      int(Qt.TextWordWrap), c).height()
                       for c, w in zip(cells, widths)) + 2 * pad

        def draw(cells, f, fill=None, row=None):
            h = row_height(cells, f)
            if self.y + h > self.bottom:
                self.new_page()
                if header:
                    draw(header, bold, ZEBRA)
            if fill is not None:
                self.p.fillRect(QRectF(0, self.y, self.width, h), fill)
            x = 0.0
            self.p.setFont(f)
            self.p.setPen(INK)
            for i, (c, w) in enumerate(zip(cells, widths)):
                self.p.setPen(MUTED if (row, i) in muted else INK)
                flags = int(Qt.TextWordWrap | (Qt.AlignRight if i in align_right else Qt.AlignLeft))
                self.p.drawText(QRectF(x + pad, self.y + pad, w - 2 * pad, h - 2 * pad), flags, c)
                x += w
            self.p.setPen(QPen(RULE, self.mm(0.15)))
            self.p.drawLine(0, int(self.y + h), int(self.width), int(self.y + h))
            self.y += h

        _ = metrics
        if header:
            draw(header, bold, ZEBRA)
        for n, row in enumerate(rows):
            draw(row, font, row=n)
        self.y += self.mm(3)

    def image(self, image, height_mm: float):
        height = self.mm(height_mm)
        self.need(height)
        target = QRectF(0, self.y, self.width, height)
        self.p.drawImage(target, image)
        self.p.setPen(QPen(RULE, self.mm(0.25)))
        self.p.drawRect(target)
        self.y += height + self.mm(3)

    def finish(self):
        self._footer()


def stamp(when: _dt.datetime) -> str:
    """'3 Oct 2026 16:07 UTC+08:00'. An offset, never a zone abbreviation:
    Manila's is "PST", which every reader outside the Philippines takes for
    Pacific time."""
    offset = when.strftime("%z")
    offset = f"UTC{offset[:3]}:{offset[3:]}" if offset else "local time"
    return f"{when.day} {when.strftime('%b %Y %H:%M')} {offset}"


def _fmt(value, unit: str = " ms") -> str:
    return "" if value is None else f"{value:.1f}{unit}"


def write_pdf(path: str, route: dict, *, target: str, trace_text: str, tool_label: str,
              origin_how: str | None, source: str, when: _dt.datetime | None = None,
              include_trace: bool = True, insight: dict | None = None,
              comparison: dict | None = None, quiet_ms: float = 15.0, hot_ms: float = 60.0,
              origin_cc: str | None = None, session: dict | None = None) -> None:
    when = when or _dt.datetime.now().astimezone()
    writer = QPdfWriter(path)
    writer.setResolution(300)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait,
                                     QMarginsF(16, 14, 16, 12), QPageLayout.Millimeter))
    writer.setTitle(f"Continuous session to {target}" if session else f"Route to {target}")
    writer.setCreator(f"{DISPLAY_NAME} {VERSION}")
    painter = QPainter(writer)
    painter.setRenderHint(QPainter.Antialiasing)
    footer = f"{DISPLAY_NAME} {VERSION}"
    flow = _Flow(writer, painter, footer)

    hops = route.get("hops") or []
    placed = [h for h in hops if h.get("lat") is not None]
    unplaced = [h for h in hops if h.get("lat") is None]
    origin = route.get("origin") or {}
    how = {"ip": "from this machine's public IP; approximate, wrong on a VPN or exit node",
           "city": "set in Settings (city)", "coords": "set in Settings (coordinates)",
           "map": "picked on the map", "atlas": "the RIPE Atlas probe's published location",
           "first-hop": "no origin set; anchored on the first located hop"}.get(
        origin_how or origin.get("source") or "", "")

    if session:
        flow.text(f"Continuous session to {target}", 20, bold=True, gap=1)
        flow.text(f"Started {stamp(when)}", 10, color=MUTED, gap=4)
    else:
        flow.text(f"Route to {target}", 20, bold=True, gap=1)
        flow.text(f"Traced {stamp(when)}", 10, color=MUTED, gap=4)
    trace_desc = {"local": f"run on this machine: {tool_label}",
                  "atlas": f"RIPE Atlas: {tool_label}",
                  "paste": f"pasted ({route.get('parser_label', '')})",
                  "file": f"opened from a file ({route.get('parser_label', '')})",
                  "watch": "continuous, built-in ICMP prober"}.get(source, tool_label)
    facts = [
        ["Target", target],
        ["Origin", f"{origin.get('label') or 'unknown'}, {how}" if how else (origin.get("label") or "unknown")],
        ["Trace", trace_desc],
        ["Hops", f"{len(hops)} hops, {len(placed)} placed on the map, {len(unplaced)} not placed"],
        ["Sources", "CAIDA Hoiho ruleset " + route["hoiho_ruleset_date"]
         if route.get("hoiho_ruleset_date") else "CAIDA Hoiho (cached answers), carrier site codes, RIPEstat"],
    ]
    flow.table(None, facts, [28, 150], size=8.5)
    for warning in route.get("warnings") or []:
        flow.text(f"Note: {warning}", 8.5, color=QColor("#a35a00"))

    credit = f"{geometry.ATTRIBUTION} · GeoNames CC BY 4.0" + (
        " · IP Geolocation by DB-IP" if mapview.uses_dbip(route) else "")
    image = mapview.render_png(route, width=1800, height=1013, title="", provenance=credit,
                               destination=target, quiet_ms=quiet_ms, hot_ms=hot_ms)
    flow.image(image, (flow.width / flow.dpi * 25.4) * 1013 / 1800)

    if insight:
        _summary_section(flow, route, insight, origin_cc)
    else:
        flow.text("Loss: " + loss_verdict(route.get("hops") or [])["text"], 8.5)

    if session:
        _session_section(flow, route, session)

    flow.heading("Hops")
    rows = []
    for h in hops:
        name = h.get("hostname") or ""
        if len(h.get("hostnames") or []) > 1:
            name += f" (+{len(h['hostnames']) - 1})"
        address = h.get("address") or "*"
        if len(h.get("addresses") or []) > 1:
            address += f" (+{len(h['addresses']) - 1})"
        detail = (((insight or {}).get("online") or {}).get("hops") or {}).get(str(h["hop"])) or {}
        src = theme.SOURCE_SHORT.get(h.get("source"), "")
        if h.get("source") == "ip-db":
            src += " DB-IP" if h.get("ip_provider") == "dbip" else " RIPEstat"
        rows.append([str(h["hop"]), h.get("place") or "not placed", src,
                     f"AS{h['asn']}" if h.get("asn") else "", RPKI_SHORT.get(detail.get("rpki"), ""),
                     name, address,
                     _fmt(h.get("min_rtt_ms")), "" if h.get("loss_pct") is None else f"{h['loss_pct']:.0f}%",
                     ", ".join(NOTE_SHORT.get(a, a) for a in h.get("annotations") or [])])
    limited = {(n, 8) for n, h in enumerate(hops) if rate_limited(h)}
    flow.table(["#", "Location", "Source", "ASN", "RPKI", "Hostname", "IP address", "RTT min", "Loss",
                "Notes"], rows, [7, 25, 18, 14, 12, 34, 22, 14, 9, 18], align_right={0, 7, 8},
               muted=limited)

    if comparison:
        _comparison_section(flow, route, comparison, target, quiet_ms, hot_ms)

    flow.heading("Unplaced hops")
    if unplaced:
        rows = []
        for h in unplaced:
            details = h.get("annotation_details") or []
            why = details[0].split(": ", 1)[-1] if details else (h.get("reason") or "")
            rows.append([str(h["hop"]), h.get("hostname") or h.get("address") or "no answer",
                         why[:1].upper() + why[1:]])
        flow.table(["#", "Answered from", "Why it is not on the map"], rows, [7, 45, 121],
                   align_right={0})
    else:
        flow.text("None: every hop that answered was placed.", 9, color=MUTED)

    details = [(h["hop"], d) for h in hops for d in h.get("annotation_details") or []
               if h.get("lat") is not None]
    if details:
        flow.heading("Reading this trace")
        for hop, detail in details:
            flow.text(f"Hop {hop}: {detail}", 8.5, gap=1)

    flow.heading("How locations were decided")
    flow.text(METHOD, 8.5, color=MUTED)
    from routemap import insight as _insight
    extra = "".join(f" {line}." for line in _insight.attributions(insight) if "DB-IP" not in line)
    flow.text("Map: Natural Earth (public domain). Cities: GeoNames, CC BY 4.0. Hostname "
              f"rules: The CAIDA UCSD Hoiho - {when.strftime('%Y-%m-%d')}, "
              "https://catalog.caida.org/dataset/hoiho. IP geolocation: RIPEstat (RIPE NCC)"
              + (" and IP Geolocation by DB-IP (db-ip.com, CC BY 4.0)"
                 if mapview.uses_dbip(route) or (insight or {}).get("as_path") else "")
              + "." + extra, 8, color=MUTED)

    if include_trace and trace_text.strip():
        flow.new_page()
        flow.text("Appendix: raw trace", 12, bold=True, gap=1)
        flow.text(tool_label or "", 8.5, color=MUTED, gap=3)
        for line in trace_text.rstrip("\n").splitlines():
            flow.text(line or " ", 7.5, mono=True, gap=0.2)
    flow.finish()
    painter.end()


def _summary_section(flow: "_Flow", route: dict, ins: dict, origin_cc: str | None) -> None:
    from routemap import insight as _insight
    s = _insight.summary(route, ins, origin_cc)
    flow.heading("Route summary")
    rows = []
    if s["as_path"]:
        rows.append(["AS path", " > ".join(
            f"AS{p['asn']} {p['short']}".strip() + (f" ({p['rpki']['label']})" if p.get("rpki") else "")
            for p in s["as_path"])])
    if s["countries"]:
        cs = ([f"{s['origin_cc']} (origin)"] if s["origin_cc"] else []) + [
            c["cc"] + (" (country only)" if c["country_only"] else "") + (" (sensitive)" if c["sensitive"] else "")
            for c in s["countries"]]
        rows.append(["Countries", " > ".join(cs)])
    if s["anycast"]:
        rows.append(["Destination", s["anycast"]])
    if (s.get("loss") or {}).get("text"):
        rows.append(["Loss", s["loss"]["text"]])
    if isinstance(s["baseline"], dict):
        rows.append(["Typical latency", f"{s['baseline']['text']} ({s['baseline']['delta']}); "
                                        f"{s['baseline']['detail']}"])
    if s["ris"]:
        r = s["ris"]
        rows.append([f"BGP view of {r['prefix']}", "; ".join(r["lines"] + ([r["visibility"]] if r["visibility"] else [])
                                                           + ([r["rpki"]["label"]] if r.get("rpki") else []))])
    if s["updates"]:
        u = s["updates"]
        rows.append(["BGP updates", f"{u['total']} in the 48 hours before the trace"
                                    + (f", a burst of {u['burst']} at trace time" if u.get("burst") else "")])
    status = s["status"]
    if status == _insight.OFF:
        rows.append(["Online details", "off (Online lookups switched off)"])
    elif status and status.startswith(_insight.UNAVAILABLE):
        rows.append(["Online details", "unavailable: RIPEstat did not answer in time"])
    flow.table(None, rows, [30, 148], size=8.5)


def _session_section(flow: "_Flow", route: dict, session: dict) -> None:
    """A continuous session: what ran, the mtr table, the changes and gaps,
    and one plot per hop over the whole session."""
    from routemap import live as _live
    snap = _live.saved_snapshot(session)
    flow.heading("Continuous session")
    why = {"duration": "reached its time limit", "count": "reached its cycle count", "user": "stopped by hand",
           "error": "stopped by an error"}.get(session.get("stopped_by"), "")
    span = ""
    if snap["now"] and snap["started"]:
        minutes = (snap["now"] - snap["started"]) / 60
        span = f", {minutes:.0f} minutes" if minutes >= 1 else f", {snap['now'] - snap['started']:.0f} seconds"
    flow.table(None, [
        ["Session", f"{session.get('cycles', 0)} cycles of {session.get('interval_s', 1):g} s{span}"
                    + (f"; {why}" if why else "")],
        ["Loss", snap["loss"].get("text", "")],
        ["Path changes", str(len(snap["changes"])) if snap["changes"] else "none"],
        ["Gaps", (f"{len(snap['gaps'])} (sleep or suspend; not counted as loss)" if snap["gaps"] else "none")],
    ], [28, 150], size=8.5)
    merged = _live.merge_hops(route.get("hops") or [], snap["hops"])
    rows, muted = [], set()
    for n, h in enumerate(merged):
        loss = "" if h.get("loss_pct") is None else f"{h['loss_pct']:.1f}%"
        if rate_limited(h):
            loss += " (rate limiting)"
            muted.add((n, 2))
        rows.append([str(h["hop"]), h.get("place") or h.get("address") or "no answer", loss,
                     str(h.get("sent") or 0), _fmt(h.get("avg_ms")), _fmt(h.get("best_ms")),
                     _fmt(h.get("worst_ms")), _fmt(h.get("stdev_ms"))])
    flow.table(["#", "Location", "Loss", "Sent", "Avg", "Best", "Worst", "StDev"], rows,
               [7, 48, 30, 12, 15, 15, 15, 15], align_right={0, 3, 4, 5, 6, 7}, muted=muted, size=7.5)
    if snap["changes"]:
        for c in snap["changes"]:
            when = _dt.datetime.fromtimestamp(c["at"]).astimezone().strftime("%H:%M:%S") if c.get("at") else ""
            flow.text(f"{when} {_live.describe_change(c)}".strip(), 8)
    for g in snap["gaps"]:
        a = _dt.datetime.fromtimestamp(g["from"]).astimezone().strftime("%H:%M:%S")
        b = _dt.datetime.fromtimestamp(g["to"]).astimezone().strftime("%H:%M:%S")
        flow.text(f"Gap {a} to {b}: the computer slept or the app was suspended; not counted as loss.", 8)
    from routemap.gui.livepanel import PingPlot
    flow.heading("RTT over the session, per hop")
    for h in merged:
        if not snap["live"].get(h["hop"]):
            continue
        plot = PingPlot()
        plot.range_index = 3
        plot.resize(1600, 260)
        plot.set_data(snap, h["hop"])
        image = plot.grab().toImage()
        flow.text(f"Hop {h['hop']}: {h.get('place') or h.get('address') or ''}", 8, bold=True, gap=0.5)
        flow.image(image, (flow.width / flow.dpi * 25.4) * 260 / 1600)


def _comparison_section(flow: "_Flow", route: dict, cmp: dict, target: str,
                        quiet_ms: float, hot_ms: float) -> None:
    flow.heading(f"Compared with {cmp.get('label', 'an earlier run')}")
    flow.text(cmp.get("summary") or "", 9, gap=2)
    image = mapview.render_png(route, width=1800, height=1013, title="",
                               provenance="Earlier run dashed and faint; changed hops ringed",
                               destination=target, quiet_ms=quiet_ms, hot_ms=hot_ms,
                               ghost=cmp.get("old_route"), marks={int(k): v for k, v in
                                                                  (cmp.get("new_marks") or {}).items()})
    flow.image(image, (flow.width / flow.dpi * 25.4) * 1013 / 1800)
    rows = []
    for c in cmp.get("changes") or []:
        kind = c["kind"]
        if kind == "removed":
            rows.append(["gone", ", ".join(c["places"]), f"hops {c['old_hops'][0]} to {c['old_hops'][-1]} then"
                         if len(c["old_hops"]) > 1 else f"hop {c['old_hops'][0]} then"])
        elif kind == "added":
            rows.append(["new", ", ".join(c["places"]), ", ".join(str(n) for n in c["new_hops"])])
        elif kind == "moved":
            rows.append(["moved", ", ".join(c["old_places"]) + " then", ", ".join(c["new_places"]) + " now"])
        elif kind == "rtt":
            rows.append(["RTT", c["place"], f"{c['old_ms']:.0f} ms then, {c['new_ms']:.0f} ms now"])
        elif kind == "asn":
            rows.append(["network", c["place"], f"AS{c['old_asn']} then, AS{c['new_asn']} now"])
    if rows:
        flow.table(["Change", "Where", "Detail"], rows, [20, 60, 98], size=8.5)
    old = cmp.get("old_route") or {}
    if old.get("hops"):
        flow.text("The earlier run", 9.5, bold=True, gap=1)
        flow.table(["#", "Location", "Source", "RTT min"],
                   [[str(h["hop"]), h.get("place") or "not placed", theme.SOURCE_SHORT.get(h.get("source"), ""),
                     _fmt(h.get("min_rtt_ms"))] for h in old["hops"]], [8, 70, 40, 20], size=8,
                   align_right={0, 3})
