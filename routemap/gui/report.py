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

from routemap.__about__ import DISPLAY_NAME, __version__
from routemap.gui import geometry, mapview, theme
from routemap.gui.hoptable import NOTE_SHORT

INK = QColor("#1f2933")
MUTED = QColor("#5f6b78")
RULE = QColor("#d3d9df")
ZEBRA = QColor("#f4f6f8")

METHOD = (
    "Each hop is placed from the router's own hostname first: CAIDA Hoiho's published "
    "naming rules, then the carrier site-code table built from each carrier's own router "
    "list. The IP geolocation database is used only when neither places the hop. Every "
    "candidate location is checked against the speed of light in fibre: a place further "
    "away than the hop's fastest round trip allows (about 100 km per millisecond, plus "
    "300 km for the origin's city-level precision) is rejected, whichever source claimed "
    "it. Private, CGNAT and reserved addresses are shown at the origin and never looked up."
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
              size: float = 7.5, align_right: set[int] = frozenset()):
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

        def draw(cells, f, fill=None):
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
                flags = int(Qt.TextWordWrap | (Qt.AlignRight if i in align_right else Qt.AlignLeft))
                self.p.drawText(QRectF(x + pad, self.y + pad, w - 2 * pad, h - 2 * pad), flags, c)
                x += w
            self.p.setPen(QPen(RULE, self.mm(0.15)))
            self.p.drawLine(0, int(self.y + h), int(self.width), int(self.y + h))
            self.y += h

        _ = metrics
        if header:
            draw(header, bold, ZEBRA)
        for row in rows:
            draw(row, font)
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
              include_trace: bool = True) -> None:
    when = when or _dt.datetime.now().astimezone()
    writer = QPdfWriter(path)
    writer.setResolution(300)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait,
                                     QMarginsF(16, 14, 16, 12), QPageLayout.Millimeter))
    writer.setTitle(f"Route to {target}")
    writer.setCreator(f"{DISPLAY_NAME} {__version__}")
    painter = QPainter(writer)
    painter.setRenderHint(QPainter.Antialiasing)
    footer = f"{DISPLAY_NAME} {__version__}"
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

    flow.text(f"Route to {target}", 20, bold=True, gap=1)
    flow.text(f"Traced {stamp(when)}", 10, color=MUTED, gap=4)
    trace_desc = {"local": f"run on this machine: {tool_label}",
                  "atlas": f"RIPE Atlas: {tool_label}",
                  "paste": f"pasted ({route.get('parser_label', '')})",
                  "file": f"opened from a file ({route.get('parser_label', '')})"}.get(source, tool_label)
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

    image = mapview.render_png(route, width=1800, height=1013, title="",
                               provenance=f"{geometry.ATTRIBUTION} · GeoNames CC BY 4.0",
                               destination=target)
    flow.image(image, (flow.width / flow.dpi * 25.4) * 1013 / 1800)

    flow.heading("Hops")
    rows = []
    for h in hops:
        name = h.get("hostname") or ""
        if len(h.get("hostnames") or []) > 1:
            name += f" (+{len(h['hostnames']) - 1})"
        address = h.get("address") or "*"
        if len(h.get("addresses") or []) > 1:
            address += f" (+{len(h['addresses']) - 1})"
        rows.append([str(h["hop"]), h.get("place") or "not placed",
                     theme.SOURCE_SHORT.get(h.get("source"), ""), name, address,
                     _fmt(h.get("min_rtt_ms")), "" if h.get("loss_pct") is None else f"{h['loss_pct']:.0f}%",
                     ", ".join(NOTE_SHORT.get(a, a) for a in h.get("annotations") or [])])
    flow.table(["#", "Location", "Source", "Hostname", "IP address", "RTT min", "Loss", "Notes"],
               rows, [7, 27, 15, 44, 25, 15, 10, 30], align_right={0, 5, 6})

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
    flow.text("Map: Natural Earth (public domain). Cities: GeoNames, CC BY 4.0. Hostname "
              f"rules: The CAIDA UCSD Hoiho - {when.strftime('%Y-%m-%d')}, "
              "https://catalog.caida.org/dataset/hoiho. IP geolocation: RIPEstat (RIPE NCC).",
              8, color=MUTED)

    if include_trace and trace_text.strip():
        flow.new_page()
        flow.text("Appendix: raw trace", 12, bold=True, gap=1)
        flow.text(tool_label or "", 8.5, color=MUTED, gap=3)
        for line in trace_text.rstrip("\n").splitlines():
            flow.text(line or " ", 7.5, mono=True, gap=0.2)
    flow.finish()
    painter.end()
