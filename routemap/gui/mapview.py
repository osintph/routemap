"""
The offline world map: Natural Earth land and borders, the route on top.

Equirectangular, because it is the projection in which "a straight segment
between two hops" means what it looks like, and because the map is a picture of
claims about cities, not a navigation chart. One scene unit is 1/SCALE of a
degree; y is negated so north is up.

ROUTES THAT CROSS THE ANTIMERIDIAN
----------------------------------
Manila to California crosses 180 degrees. Drawn naively, the segment runs the
whole width of the map the wrong way. So each hop's longitude is unwrapped
against the previous one (shifted by 360 until the step is under 180 degrees),
and the land is drawn three times side by side, so the route continues across
the seam over real coastline.

MARKERS
-------
Constant screen size whatever the zoom (they ignore the view transform),
numbered by hop, coloured by the source that placed the hop. Consecutive hops in
the same place collapse into one marker labelled with the range ("10-11"), and
the tooltip lists every hop in it. A hop that answered from several routers
(ECMP) is one marker whose tooltip shows every address and every candidate
location with the reason it was accepted or rejected.
"""
from __future__ import annotations

import html
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath,
                           QPen, QPolygonF)
from PySide6.QtWidgets import (QFrame, QGraphicsItem, QGraphicsObject, QGraphicsPathItem,
                               QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QToolButton,
                               QVBoxLayout, QWidget)

from routemap.gui import geometry, theme

SCALE = 4.0           # scene units per degree
WORLD_W = 360 * SCALE
MIN_SPAN_DEG = 6.0    # never zoom a fit tighter than this many degrees


def to_scene(lon: float, lat: float) -> QPointF:
    return QPointF(lon * SCALE, -lat * SCALE)


# ------------------------------------------------------------------ the route ---

def route_groups(route: dict) -> list[dict]:
    """Placed hops as map points: unwrapped, grouped, gaps marked.

    Pure, so tests can check grouping and the antimeridian without a display.
    Returns [{"hops": [hop, ...], "lat", "lon", "source", "gap_before",
    "at_origin"}], in path order. The origin is not a group; a group that sits
    exactly on it (the local hops) is flagged ``at_origin``.
    """
    origin = route.get("origin") or {}
    prev_lon = origin.get("lon")
    origin_key = None
    if origin.get("lat") is not None:
        origin_key = (round(origin["lat"], 3), round(origin["lon"], 3))
    groups: list[dict] = []
    gap = False
    for hop in route.get("hops") or []:
        if hop.get("lat") is None:
            gap = True
            continue
        lat, lon = float(hop["lat"]), float(hop["lon"])
        if prev_lon is not None:
            while lon - prev_lon > 180:
                lon -= 360
            while lon - prev_lon < -180:
                lon += 360
        key = (round(lat, 3), round(lon, 3))
        if groups and not gap and (round(groups[-1]["lat"], 3), round(groups[-1]["lon"], 3)) == key:
            groups[-1]["hops"].append(hop)
        else:
            groups.append({"hops": [hop], "lat": lat, "lon": lon,
                           "source": hop.get("source"), "gap_before": gap and bool(groups),
                           "at_origin": origin_key is not None and key == origin_key})
        gap = False
        prev_lon = lon
    return groups


def hop_range(hops: list[dict]) -> str:
    first, last = hops[0]["hop"], hops[-1]["hop"]
    return str(first) if first == last else f"{first}-{last}"


def _fmt_ms(value) -> str:
    return "-" if value is None else f"{value:.1f} ms"


def group_tooltip(group: dict, origin_label: str | None = None) -> str:
    """Rich-text tooltip for one marker: every hop in it, and ECMP candidates."""
    rows = []
    if group.get("at_origin") and origin_label:
        rows.append(f"<b>Origin:</b> {html.escape(origin_label)}")
    for hop in group["hops"]:
        name = hop.get("hostname") or hop.get("address") or "no answer"
        line = (f"<b>Hop {hop['hop']}</b> {html.escape(name)}"
                f"<br>&nbsp;&nbsp;{html.escape(hop.get('place') or 'not placed')}"
                f" &middot; {html.escape(theme.SOURCE_LABELS.get(hop.get('source'), ''))}"
                f" &middot; min {_fmt_ms(hop.get('min_rtt_ms'))}")
        if len(hop.get("addresses") or []) > 1 or len(hop.get("hostnames") or []) > 1:
            line += ("<br>&nbsp;&nbsp;<i>Answered from more than one router (ECMP). "
                     "Candidate locations:</i>"
                     "<table cellspacing='0' cellpadding='1' style='margin-left:14px'>")
            located = [c for c in hop.get("candidates") or [] if c.get("lat") is not None]
            for c in located:
                who = c.get("hostname") or c.get("address") or "?"
                if c.get("accepted"):
                    verdict = "<b>used</b>"
                elif c.get("distance_km") is not None and c.get("rtt_budget_km") is not None:
                    verdict = (f"ruled out: {c['distance_km']:,.0f} km away, the fastest probe "
                               f"allows {c['rtt_budget_km']:,.0f} km")
                else:
                    verdict = html.escape(c.get("why") or "not used")
                line += (f"<tr><td>{html.escape(who)}&nbsp;&nbsp;</td>"
                         f"<td>{html.escape(c.get('place') or '')}&nbsp;&nbsp;</td>"
                         f"<td>{verdict}</td></tr>")
            line += "</table>"
            missed = [c for c in hop.get("candidates") or []
                      if c.get("lat") is None and c.get("source") == "hoiho"]
            if missed:
                line += (f"&nbsp;&nbsp;<span style='color:#888'>CAIDA Hoiho had no rule for "
                         f"{'either hostname' if len(missed) == 2 else str(len(missed)) + ' of them'}"
                         f".</span>")
        for note in hop.get("annotation_details") or []:
            line += f"<br>&nbsp;&nbsp;<span style='color:#888'>{html.escape(note)}</span>"
        rows.append(line)
    return "<br>".join(rows)


# ------------------------------------------------------------------- items ---

class LeaderItem(QGraphicsItem):
    """A moved marker's true point and the line to where its pill went.

    Its own item, one layer below every pill, so a leader or a dot can never
    be drawn over another marker's number.
    """

    def __init__(self, marker: "MarkerItem"):
        super().__init__()
        self.marker = marker
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setZValue(8)

    def boundingRect(self) -> QRectF:
        off = self.marker.offset
        return QRectF(QPointF(0, 0), off).normalized().adjusted(-5, -5, 5, 5)

    def paint(self, painter: QPainter, option, widget=None):
        m = self.marker
        if m.offset.isNull():
            return
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(m.palette.route, 1.2 * m.size))
        painter.drawLine(QPointF(0, 0), m.offset)
        painter.setPen(QPen(m.palette.marker_ring, 1.0))
        painter.setBrush(m.palette.origin if m.origin else m.color)
        painter.drawEllipse(QPointF(0, 0), 3.2 * m.size, 3.2 * m.size)


class MarkerItem(QGraphicsObject):
    """A numbered pill at constant screen size."""

    def __init__(self, label: str, color: QColor, palette: theme.Palette, *,
                 origin: bool = False, caption: str | None = None, tooltip: str = "",
                 size: float = 1.0):
        super().__init__()
        self.label, self.color, self.palette = label, color, palette
        self.origin, self.caption = origin, caption
        self.hovered = False
        self.size = size
        # Where the pill is drawn relative to its true point, in device pixels,
        # when it had to move aside to stay readable. See declutter().
        self.offset = QPointF(0, 0)
        self.leader: LeaderItem | None = None
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(20 if origin else 10)
        if tooltip:
            self.setToolTip(tooltip)
        self.font = QFont()
        self.font.setPointSizeF(8.5 * size)
        self.font.setBold(True)
        self.caption_font = QFont()
        self.caption_font.setPointSizeF(8.5 * size)
        metrics = QFontMetricsF(self.font)
        self.h = 20.0 * size
        self.w = max(self.h, metrics.horizontalAdvance(label) + 12 * size) if label else 14.0 * size
        if not label:
            self.h = 14.0 * size

    def footprint(self) -> QRectF:
        """The pill and its caption around (0, 0), for collision tests."""
        rect = QRectF(-self.w / 2 - 2, -self.h / 2 - 2, self.w + 4, self.h + 4)
        if self.caption:
            metrics = QFontMetricsF(self.caption_font)
            cw = metrics.horizontalAdvance(self.caption) + 14
            rect = rect.united(QRectF(-cw / 2, self.h / 2, cw, metrics.height() + 8))
        return rect

    def set_offset(self, offset: QPointF):
        if self.leader is None and self.scene() is not None:
            self.leader = LeaderItem(self)
            self.leader.setPos(self.pos())
            self.scene().addItem(self.leader)
        if offset != self.offset:
            self.prepareGeometryChange()
            if self.leader is not None:
                self.leader.prepareGeometryChange()
            self.offset = QPointF(offset)
            self.update()
            if self.leader is not None:
                self.leader.update()

    def boundingRect(self) -> QRectF:
        return self.footprint().adjusted(-3, -3, 3, 3).translated(self.offset)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.footprint().translated(self.offset))
        return path

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.offset.isNull():
            # The true point and the leader are drawn by self.leader, below.
            painter.translate(self.offset)
        grow = 1.12 if self.hovered else 1.0
        w, h = self.w * grow, self.h * grow
        rect = QRectF(-w / 2, -h / 2, w, h)
        ring = QPen(self.palette.marker_ring, 2.0)
        if self.origin:
            painter.setPen(QPen(self.palette.origin, 2.0))
            painter.setBrush(QBrush(self.palette.marker_ring))
            painter.drawRoundedRect(rect, h / 2, h / 2)
            if self.label:
                painter.setFont(self.font)
                painter.setPen(self.palette.origin)
                painter.drawText(rect, Qt.AlignCenter, self.label)
            else:
                painter.setBrush(self.palette.origin)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(0, 0), 3.5, 3.5)
        else:
            painter.setPen(ring)
            painter.setBrush(QBrush(self.color))
            painter.drawRoundedRect(rect, h / 2, h / 2)
            painter.setFont(self.font)
            painter.setPen(self.palette.marker_text)
            painter.drawText(rect, Qt.AlignCenter, self.label)
        if self.caption:
            painter.setFont(self.caption_font)
            metrics = QFontMetricsF(self.caption_font)
            cw = metrics.horizontalAdvance(self.caption) + 12
            crect = QRectF(-cw / 2, h / 2 + 3, cw, metrics.height() + 4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.palette.overlay_bg)
            painter.drawRoundedRect(crect, 4, 4)
            painter.setPen(self.palette.overlay_fg)
            painter.drawText(crect, Qt.AlignCenter, self.caption)

    def hoverEnterEvent(self, event):
        self.hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self.hovered = False
        self.update()


def _world_paths() -> tuple[QPainterPath, QPainterPath, QPainterPath]:
    world = geometry.world()

    def rings(polys, close: bool) -> QPainterPath:
        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)
        for ring in polys:
            poly = QPolygonF([to_scene(lon, lat) for lon, lat in ring])
            if close:
                path.addPolygon(poly)
                path.closeSubpath()
            else:
                path.moveTo(poly[0])
                for point in list(poly)[1:]:
                    path.lineTo(point)
        return path

    return rings(world["land"], True), rings(world["lakes"], True), rings(world["borders"], False)


_PATHS = None


def world_paths():
    global _PATHS
    if _PATHS is None:
        _PATHS = _world_paths()
    return _PATHS


def build_scene(palette: theme.Palette) -> QGraphicsScene:
    scene = QGraphicsScene()
    scene.setBackgroundBrush(palette.ocean)
    scene.setSceneRect(QRectF(-540 * SCALE, -90 * SCALE, 1080 * SCALE, 180 * SCALE))
    land, lakes, borders = world_paths()
    coast_pen = QPen(palette.coast, 0.8)
    coast_pen.setCosmetic(True)
    border_pen = QPen(palette.border, 0.7)
    border_pen.setCosmetic(True)
    for offset in (-WORLD_W, 0.0, WORLD_W):
        item = QGraphicsPathItem(land)
        item.setPen(coast_pen)
        item.setBrush(palette.land)
        item.setPos(offset, 0)
        scene.addItem(item)
        lake = QGraphicsPathItem(lakes)
        lake.setPen(coast_pen)
        lake.setBrush(palette.ocean)
        lake.setPos(offset, 0)
        scene.addItem(lake)
        line = QGraphicsPathItem(borders)
        line.setPen(border_pen)
        line.setPos(offset, 0)
        scene.addItem(line)
    return scene


def draw_route(scene: QGraphicsScene, route: dict, palette: theme.Palette,
               destination_label: str | None = None, size: float = 1.0) -> tuple[QRectF, list]:
    """Add the route to *scene*. Returns (the scene rect it covers, its markers)."""
    markers: list[MarkerItem] = []
    origin = route.get("origin") or {}
    groups = route_groups(route)
    points = []
    if origin.get("lat") is not None:
        points.append(to_scene(origin["lon"], origin["lat"]))

    pen = QPen(palette.route, 2.0)
    pen.setCosmetic(True)
    pen.setCapStyle(Qt.RoundCap)
    gap_pen = QPen(palette.route_gap, 1.6, Qt.DashLine)
    gap_pen.setCosmetic(True)

    prev = points[0] if points else None
    for group in groups:
        here = to_scene(group["lon"], group["lat"])
        if prev is not None and here != prev:
            path = QPainterPath(prev)
            path.lineTo(here)
            item = QGraphicsPathItem(path)
            item.setPen(gap_pen if group["gap_before"] else pen)
            item.setZValue(5)
            scene.addItem(item)
        prev = here
        points.append(here)

    origin_label = origin.get("label")
    origin_drawn = False
    for index, group in enumerate(groups):
        last = index == len(groups) - 1
        tip = group_tooltip(group, origin_label)
        caption = None
        if group["at_origin"] and not origin_drawn:
            marker = MarkerItem(hop_range(group["hops"]), palette.origin, palette, origin=True,
                                caption=_short(origin_label), tooltip=tip, size=size)
            origin_drawn = True
        else:
            if last and destination_label:
                caption = destination_label
            color = palette.sources.get(group["source"], palette.sources["unresolved"])
            marker = MarkerItem(hop_range(group["hops"]), color, palette, caption=caption,
                                tooltip=tip, size=size)
        marker.order = group["hops"][0]["hop"]
        marker.setPos(to_scene(group["lon"], group["lat"]))
        scene.addItem(marker)
        markers.append(marker)
    if origin.get("lat") is not None and not origin_drawn:
        marker = MarkerItem("", palette.origin, palette, origin=True, caption=_short(origin_label),
                            tooltip=f"<b>Origin:</b> {html.escape(origin_label or '')}", size=size)
        marker.order = 0
        marker.setPos(to_scene(origin["lon"], origin["lat"]))
        scene.addItem(marker)
        markers.append(marker)

    if not points:
        return QRectF(), markers
    xs = [p.x() for p in points]
    ys = [p.y() for p in points]
    return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)), markers


def _short(label: str | None) -> str | None:
    """'Manila, NCR, PH' -> 'Manila, PH' for a map caption."""
    if not label:
        return None
    parts = [p.strip() for p in label.split(",")]
    return f"{parts[0]}, {parts[-1]}" if len(parts) > 2 else label


def declutter(markers: list, to_device) -> None:
    """Move markers aside, in screen space, until none overlaps another.

    Markers keep their true point (marked with a dot and a leader line) and the
    pill moves to the nearest free spot on rings around it. The origin goes
    first and never moves; then hops in path order, so the order of the route
    decides who keeps their spot. Runs after every zoom, because overlap is a
    property of the zoom level, not of the route.
    """
    placed: list[QRectF] = []
    ordered = sorted(markers, key=lambda m: (not m.origin, getattr(m, "order", 0)))
    anchors = {id(m): to_device(m.pos()) for m in ordered}
    for marker in ordered:
        anchor = anchors[id(marker)]
        foot = marker.footprint()
        # Other markers' true points must stay visible too.
        dots = [QRectF(anchors[id(o)].x() - 4, anchors[id(o)].y() - 4, 8, 8)
                for o in ordered if o is not marker]
        chosen = QPointF(0, 0)
        if any(foot.translated(anchor).intersects(r) for r in placed):
            step = max(foot.width(), foot.height()) * 0.75 + 6
            found = False
            for ring in range(1, 9):
                radius = step * ring
                count = 8 * ring
                for k in range(count):
                    angle = -math.pi / 4 + 2 * math.pi * k / count
                    candidate = QPointF(radius * math.cos(angle), -radius * math.sin(angle))
                    rect = foot.translated(anchor + candidate)
                    if any(rect.intersects(r) for r in placed):
                        continue
                    if any(rect.intersects(d) for d in dots):
                        continue
                    chosen, found = candidate, True
                    break
                if found:
                    break
        marker.set_offset(chosen)
        placed.append(foot.translated(anchor + chosen))


def padded(rect: QRectF, aspect: float | None = None) -> QRectF:
    """A route rect with breathing room, never tighter than MIN_SPAN_DEG."""
    min_span = MIN_SPAN_DEG * SCALE
    w, h = max(rect.width(), min_span), max(rect.height(), min_span * 0.6)
    cx, cy = rect.center().x(), rect.center().y()
    w, h = w * 1.25 + 8 * SCALE, h * 1.35 + 8 * SCALE
    if aspect:
        if w / h < aspect:
            w = h * aspect
        else:
            h = w / aspect
    top = max(-90 * SCALE, cy - h / 2)
    if top + h > 90 * SCALE:
        top = max(-90 * SCALE, 90 * SCALE - h)
    return QRectF(cx - w / 2, top, w, min(h, 180 * SCALE))


# -------------------------------------------------------------------- view ---

class _Overlay(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("overlay")
        self.setAttribute(Qt.WA_StyledBackground, True)


class MapView(QGraphicsView):
    """The interactive map. ``set_route`` draws, the buttons fit and reset."""

    originPicked = Signal(float, float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.route: dict | None = None
        self.origin_only: tuple | None = None
        self.destination: str | None = None
        self.route_rect = QRectF()
        self.markers: list = []
        self.picking = False
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumSize(QSize(360, 240))
        self._build_overlays()
        self._rebuild()

    # ---- overlays
    def _build_overlays(self):
        self.controls = _Overlay(self)
        box = QVBoxLayout(self.controls)
        box.setContentsMargins(4, 4, 4, 4)
        box.setSpacing(2)
        self.btn_in = self._tool("+", "Zoom in", lambda: self.zoom(1.4))
        self.btn_out = self._tool("−", "Zoom out", lambda: self.zoom(1 / 1.4))
        self.btn_fit = self._tool("Fit", "Fit the route", self.fit_route)
        self.btn_world = self._tool("World", "Show the whole world", self.reset_view)
        for button in (self.btn_in, self.btn_out, self.btn_fit, self.btn_world):
            box.addWidget(button)

        self.legend = _Overlay(self)
        self.legend_layout = QVBoxLayout(self.legend)
        self.legend_layout.setContentsMargins(10, 8, 10, 8)
        self.legend_layout.setSpacing(3)

        self.attribution = QLabel("Natural Earth · GeoNames", self)
        self.attribution.setObjectName("attribution")

        self.card = _Overlay(self)
        card = QVBoxLayout(self.card)
        card.setContentsMargins(22, 18, 22, 18)
        card.setSpacing(6)
        self.card_title = QLabel(self.card)
        self.card_title.setObjectName("cardTitle")
        self.card_body = QLabel(self.card)
        self.card_body.setWordWrap(True)
        self.card_body.setObjectName("cardBody")
        self.card_body.setTextFormat(Qt.RichText)
        card.addWidget(self.card_title)
        card.addWidget(self.card_body)
        self.card.hide()

    def _tool(self, text, tip, slot):
        button = QToolButton(self.controls)
        button.setText(text)
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.setMinimumWidth(46)
        button.clicked.connect(slot)
        return button

    def _style_overlays(self):
        p = self.palette_
        bg = p.overlay_bg
        css = (
            f"#overlay {{ background: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()});"
            f" border: 1px solid {p.coast.name()}; border-radius: 8px; }}"
            f"#overlay QToolButton {{ color: {p.overlay_fg.name()}; font-weight: 600;"
            f" padding: 3px 6px; border-radius: 5px; }}"
            f"#overlay QToolButton:hover {{ background: {p.border.name()}; }}"
            f"#overlay QLabel {{ color: {p.overlay_fg.name()}; background: transparent; }}"
            f"#cardTitle {{ font-size: 16px; font-weight: 600; }}"
            f"#cardBody {{ color: {p.overlay_muted.name()}; }}"
            f"#attribution {{ color: {p.overlay_muted.name()}; background: transparent;"
            f" font-size: 10px; }}"
        )
        for widget in (self.controls, self.legend, self.card, self.attribution):
            widget.setStyleSheet(css)

    def _fill_legend(self, sources: list[str]):
        while self.legend_layout.count():
            item = self.legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        title = QLabel("<b>Placed by</b>")
        self.legend_layout.addWidget(title)
        for source in sources:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(6)
            dot = QLabel()
            dot.setFixedSize(10, 10)
            color = self.palette_.sources[source]
            dot.setStyleSheet(f"background: {color.name()}; border-radius: 5px;")
            line.addWidget(dot)
            line.addWidget(QLabel(theme.SOURCE_LABELS[source]))
            line.addStretch(1)
            self.legend_layout.addWidget(row)
        self.legend.adjustSize()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_overlays()
        self._declutter()

    def _declutter(self):
        if self.markers:
            declutter(self.markers,
                      lambda point: QPointF(self.mapFromScene(point)))

    def _place_overlays(self):
        m = 12
        self.controls.adjustSize()
        self.controls.move(self.width() - self.controls.width() - m, m)
        self.legend.adjustSize()
        self.legend.move(m, self.height() - self.legend.height() - m)
        self.attribution.adjustSize()
        self.attribution.move(self.width() - self.attribution.width() - m,
                              self.height() - self.attribution.height() - 6)
        self.card.setFixedWidth(min(440, self.width() - 2 * m))
        self.card.adjustSize()
        # Below the middle, so the origin marker (which the world view centres)
        # stays visible above it.
        self.card.move((self.width() - self.card.width()) // 2,
                       min(self.height() - self.card.height() - 56, int(self.height() * 0.58)))

    # ---- content
    def _rebuild(self):
        self.palette_ = theme.current()
        self.setScene(build_scene(self.palette_))
        self._style_overlays()
        self.route_rect = QRectF()
        self.markers = []
        if self.route is not None:
            self.route_rect, self.markers = draw_route(self.scene(), self.route, self.palette_,
                                                       self.destination)
            used = [s for s in ("hoiho", "site-code", "ip-db", "local")
                    if any(h.get("source") == s for h in self.route.get("hops") or [])]
            self._fill_legend(used)
            self.legend.show()
        else:
            self.legend.hide()
            if self.origin_only is not None:
                lat, lon, label = self.origin_only
                fake = {"origin": {"lat": lat, "lon": lon, "label": label}, "hops": []}
                self.route_rect, self.markers = draw_route(self.scene(), fake, self.palette_)
        self._place_overlays()

    def theme_changed(self):
        self._rebuild()
        self.fit_route()

    def set_route(self, route: dict | None, destination: str | None = None):
        self.route, self.destination = route, destination
        self.origin_only = None
        self._rebuild()
        self.fit_route()

    def set_origin(self, lat: float, lon: float, label: str | None):
        self.route = None
        self.origin_only = (lat, lon, label)
        self._rebuild()
        self.reset_view()

    def show_card(self, title: str, body: str):
        self.card_title.setText(title)
        self.card_body.setText(body)
        self.card.show()
        self._place_overlays()

    def hide_card(self):
        self.card.hide()

    # ---- navigation
    def zoom(self, factor: float):
        current = self.transform().m11()
        floor = self.viewport().height() / (180 * SCALE)
        target = max(floor, min(current * factor, 400.0))
        self.scale(target / current, target / current)
        self._declutter()

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120.0
        if steps:
            self.zoom(1.25 ** steps)

    def fit_route(self):
        if self.route_rect.isNull() and self.route is None:
            self.reset_view()
            return
        aspect = max(0.2, self.viewport().width() / max(1, self.viewport().height()))
        self.fitInView(padded(self.route_rect, aspect), Qt.KeepAspectRatio)
        self._declutter()

    def reset_view(self):
        """The world, filling the pane: height-led, so a tall pane shows a
        region rather than a thin strip; the map repeats sideways anyway."""
        center_lon = 0.0
        if not self.route_rect.isNull() or self.origin_only:
            center_lon = self.route_rect.center().x() / SCALE
        aspect = max(0.2, self.viewport().width() / max(1, self.viewport().height()))
        height = 140.0
        width = min(360.0 * 1.6, max(height * aspect, 120.0))
        rect = QRectF((center_lon - width / 2) * SCALE, -80 * SCALE, width * SCALE, height * SCALE)
        self.fitInView(rect, Qt.KeepAspectRatio)
        self._declutter()

    # ---- origin picking (Settings > Origin > pick on map)
    def mousePressEvent(self, event):
        if self.picking and event.button() == Qt.LeftButton:
            point = self.mapToScene(event.position().toPoint())
            lon = ((point.x() / SCALE + 180) % 360) - 180
            lat = max(-90.0, min(90.0, -point.y() / SCALE))
            self.originPicked.emit(round(lat, 2), round(lon, 2))
            return
        super().mousePressEvent(event)


# ------------------------------------------------------------------ export ---

def render_png(route: dict, *, width: int = 1600, height: int = 900, dark: bool = False,
               title: str = "", provenance: str = "", destination: str | None = None) -> QImage:
    """The full route extent rendered off-screen, with legend and provenance."""
    palette = theme.DARK if dark else theme.LIGHT
    scene = build_scene(palette)
    rect, markers = draw_route(scene, route, palette, destination, size=1.35)
    source = padded(rect, width / height)
    k = min(width / source.width(), height / source.height())
    ox = (width - source.width() * k) / 2
    oy = (height - source.height() * k) / 2
    declutter(markers, lambda point: QPointF((point.x() - source.left()) * k + ox,
                                             (point.y() - source.top()) * k + oy))
    image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    image.fill(palette.ocean)
    painter = QPainter(image)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    scene.render(painter, QRectF(0, 0, width, height), source, Qt.KeepAspectRatio)

    # Legend, bottom left.
    used = [s for s in ("hoiho", "site-code", "ip-db", "local")
            if any(h.get("source") == s for h in route.get("hops") or [])]
    font = QFont()
    font.setPointSizeF(13)
    painter.setFont(font)
    metrics = QFontMetricsF(font)
    line_h = metrics.height() + 6
    box_w = max([metrics.horizontalAdvance(theme.SOURCE_LABELS[s]) for s in used] + [120]) + 52
    box_h = line_h * (len(used) + 1) + 18
    box = QRectF(24, height - box_h - 24, box_w, box_h)
    painter.setPen(QPen(palette.coast, 1))
    painter.setBrush(palette.overlay_bg)
    painter.drawRoundedRect(box, 10, 10)
    painter.setPen(palette.overlay_fg)
    bold = QFont(font)
    bold.setBold(True)
    painter.setFont(bold)
    painter.drawText(QPointF(box.left() + 16, box.top() + 12 + metrics.ascent()), "Placed by")
    painter.setFont(font)
    for i, source in enumerate(used):
        y = box.top() + 12 + line_h * (i + 1)
        painter.setPen(Qt.NoPen)
        painter.setBrush(palette.sources[source])
        painter.drawEllipse(QPointF(box.left() + 22, y + metrics.height() / 2), 6, 6)
        painter.setPen(palette.overlay_fg)
        painter.drawText(QPointF(box.left() + 38, y + metrics.ascent()), theme.SOURCE_LABELS[source])

    # Title top left, provenance bottom right.
    if title:
        tfont = QFont()
        tfont.setPointSizeF(20)
        tfont.setBold(True)
        painter.setFont(tfont)
        tm = QFontMetricsF(tfont)
        tw = tm.horizontalAdvance(title) + 32
        painter.setPen(Qt.NoPen)
        painter.setBrush(palette.overlay_bg)
        painter.drawRoundedRect(QRectF(24, 24, tw, tm.height() + 16), 10, 10)
        painter.setPen(palette.overlay_fg)
        painter.drawText(QPointF(40, 32 + tm.ascent()), title)
    if provenance:
        pfont = QFont()
        pfont.setPointSizeF(11)
        painter.setFont(pfont)
        pm = QFontMetricsF(pfont)
        pw = pm.horizontalAdvance(provenance)
        painter.setPen(palette.overlay_muted)
        painter.drawText(QPointF(width - pw - 24, height - 20), provenance)
    painter.end()
    return image
