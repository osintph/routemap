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

def is_country_only(hop: dict) -> bool:
    return hop.get("precision") == "country"


def route_groups(route: dict) -> list[dict]:
    """Placed hops as map points: unwrapped, grouped, gaps marked.

    Pure, so tests can check grouping and the antimeridian without a display.
    Returns [{"hops", "lat", "lon", "source", "gap_before", "at_origin",
    "country_only", "silent"}], in path order. Hops placed only to country level
    never merge with city hops. Hops after the last placed one that did not
    answer form one final "silent" group anchored on the last point, so a trace
    that is still running (or ended in silence) shows them at once.
    """
    origin = route.get("origin") or {}
    prev_lon = origin.get("lon")
    origin_key = None
    if origin.get("lat") is not None:
        origin_key = (round(origin["lat"], 3), round(origin["lon"], 3))
    groups: list[dict] = []
    gap = False
    trailing: list[dict] = []
    for hop in route.get("hops") or []:
        if hop.get("lat") is None:
            gap = True
            trailing.append(hop)
            continue
        trailing = []
        lat, lon = float(hop["lat"]), float(hop["lon"])
        if prev_lon is not None:
            while lon - prev_lon > 180:
                lon -= 360
            while lon - prev_lon < -180:
                lon += 360
        key = (round(lat, 3), round(lon, 3))
        country = is_country_only(hop)
        last = groups[-1] if groups else None
        if (last is not None and not gap and last["country_only"] == country
                and (round(last["lat"], 3), round(last["lon"], 3)) == key):
            last["hops"].append(hop)
        else:
            groups.append({"hops": [hop], "lat": lat, "lon": lon, "source": hop.get("source"),
                           "gap_before": gap and bool(groups), "country_only": country,
                           "silent": False,
                           "at_origin": origin_key is not None and key == origin_key and not country})
        gap = False
        prev_lon = lon
    if trailing:
        anchor = groups[-1] if groups else None
        lat = anchor["lat"] if anchor else origin.get("lat")
        lon = anchor["lon"] if anchor else origin.get("lon")
        if lat is not None:
            groups.append({"hops": trailing, "lat": lat, "lon": lon, "source": "unresolved",
                           "gap_before": True, "country_only": False, "silent": True,
                           "at_origin": False})
    return groups


def hop_range(hops: list[dict]) -> str:
    first, last = hops[0]["hop"], hops[-1]["hop"]
    return str(first) if first == last else f"{first}-{last}"


def _fmt_ms(value) -> str:
    return "-" if value is None else f"{value:.1f} ms"


def place_label(hop: dict) -> str:
    place = hop.get("place") or ("not placed" if hop.get("lat") is None else "")
    return f"{place} (country only)" if is_country_only(hop) else place


def source_label(hop: dict) -> str:
    short = theme.SOURCE_SHORT.get(hop.get("source"), hop.get("source") or "")
    return f"{short}, country only" if is_country_only(hop) else short


def group_tooltip(group: dict, origin_label: str | None = None) -> str:
    """The same fields as the hop table row, for every hop in the marker."""
    from routemap.gui.hoptable import NOTE_SHORT

    esc = html.escape
    rows = []
    if group.get("at_origin") and origin_label:
        rows.append(f"<p style='margin:0 0 4px 0'><b>Origin:</b> {esc(origin_label)}</p>")
    if group.get("silent"):
        answered = any(h.get("addresses") for h in group["hops"])
        rows.append("<p style='margin:0 0 4px 0'><i>"
                    + ("Not placed: some answered but no source could place them, and some "
                       "have not replied." if answered else "No reply from these hops yet, or at all.")
                    + "</i></p>")
    for hop in group["hops"]:
        extra_ip = len(hop.get("addresses") or []) - 1
        extra_name = len(hop.get("hostnames") or []) - 1
        notes = ", ".join(NOTE_SHORT.get(a, a) for a in hop.get("annotations") or [])
        loss = hop.get("loss_pct")
        cells = [
            ("Hop", str(hop["hop"])),
            ("Location", place_label(hop)),
            ("Hostname", (hop.get("hostname") or "-") + (f" (+{extra_name})" if extra_name > 0 else "")),
            ("IP address", (hop.get("address") or "*") + (f" (+{extra_ip})" if extra_ip > 0 else "")),
            ("RTT", f"min {_fmt_ms(hop.get('min_rtt_ms'))}, avg {_fmt_ms(hop.get('avg_rtt_ms'))}"),
            ("Loss", "-" if loss is None else f"{loss:.0f}%"),
            ("Source", source_label(hop)),
        ]
        if notes:
            cells.append(("Notes", notes))
        if hop.get("lat") is None and hop.get("reason"):
            cells.append(("Why", hop["reason"]))
        table = "".join(f"<tr><td style='color:#888;padding-right:10px'>{esc(k)}</td>"
                        f"<td>{esc(v)}</td></tr>" for k, v in cells)
        block = f"<table cellspacing='0' cellpadding='1'>{table}</table>"
        if extra_ip > 0 or extra_name > 0:
            block += ("<p style='margin:4px 0 0 0'><i>Answered from more than one router (ECMP). "
                      "Candidate locations:</i></p><table cellspacing='0' cellpadding='1'>")
            for c in [c for c in hop.get("candidates") or [] if c.get("lat") is not None]:
                who = c.get("hostname") or c.get("address") or "?"
                if c.get("accepted"):
                    verdict = "<b>used</b>"
                elif c.get("distance_km") is not None and c.get("rtt_budget_km") is not None:
                    verdict = (f"ruled out: {c['distance_km']:,.0f} km away, the fastest probe "
                               f"allows {c['rtt_budget_km']:,.0f} km")
                else:
                    verdict = esc(c.get("why") or "not used")
                block += (f"<tr><td>{esc(who)}&nbsp;&nbsp;</td><td>{esc(c.get('place') or '')}"
                          f"&nbsp;&nbsp;</td><td>{verdict}</td></tr>")
            block += "</table>"
        rows.append(block)
    return "<hr>".join(rows)


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
        pen = QPen(m.palette.route_gap if m.silent else m.palette.route, 1.2 * m.size)
        if m.silent:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(0, 0), m.offset)
        painter.setPen(QPen(m.palette.marker_ring, 1.0))
        painter.setBrush(m.palette.origin if m.origin else m.color)
        painter.drawEllipse(QPointF(0, 0), 3.2 * m.size, 3.2 * m.size)


class MarkerItem(QGraphicsObject):
    """A numbered pill at constant screen size. Click selects its hops.

    Filled: placed to a city. Hollow with a coloured outline: placed only to a
    country (the point is a centroid). Hollow, grey and dashed: hops that have
    not answered (yet), shown beside the last placed point.
    """

    clicked = Signal(list)

    def __init__(self, label: str, color: QColor, palette: theme.Palette, *,
                 origin: bool = False, caption: str | None = None, tooltip: str = "",
                 size: float = 1.0, hollow: bool = False, silent: bool = False,
                 hops: list[int] | None = None):
        super().__init__()
        self.hollow, self.silent = hollow, silent
        self.hops = list(hops or [])
        self.selected = False
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
        elif self.hollow or self.silent:
            outline = self.palette.route_gap if self.silent else self.color
            pen = QPen(outline, 2.0 * self.size)
            if self.silent:
                pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(self.palette.overlay_bg))
            painter.drawRoundedRect(rect, h / 2, h / 2)
            painter.setFont(self.font)
            painter.setPen(outline if self.silent else self.color.darker(115)
                           if not self.palette.dark else self.color)
            painter.drawText(rect, Qt.AlignCenter, self.label)
        else:
            painter.setPen(ring)
            painter.setBrush(QBrush(self.color))
            painter.drawRoundedRect(rect, h / 2, h / 2)
            painter.setFont(self.font)
            painter.setPen(self.palette.marker_text)
            painter.drawText(rect, Qt.AlignCenter, self.label)
        if self.selected:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(self.palette.route, 2.5 * self.size))
            grow_px = 4 * self.size
            painter.drawRoundedRect(rect.adjusted(-grow_px, -grow_px, grow_px, grow_px),
                                    h / 2 + grow_px, h / 2 + grow_px)
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

    def set_selected(self, on: bool):
        if on != self.selected:
            self.selected = on
            self.setZValue((30 if on else (20 if self.origin else 10)))
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.hops:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.hops:
            self.clicked.emit(self.hops)
            event.accept()
            return
        super().mouseReleaseEvent(event)

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
    """Add the route to *scene*. Returns (the rect to fit, the items added).

    The rect covers the origin and every city-level hop. Country-only hops and
    silent hops do not stretch it: a country centroid is not a place the packet
    is known to have been.
    """
    items: list = []
    origin = route.get("origin") or {}
    groups = route_groups(route)
    fit_points, points = [], []
    if origin.get("lat") is not None:
        start = to_scene(origin["lon"], origin["lat"])
        fit_points.append(start)
        points.append(start)

    pen = QPen(palette.route, 2.0)
    pen.setCosmetic(True)
    pen.setCapStyle(Qt.RoundCap)
    gap_pen = QPen(palette.route_gap, 1.6, Qt.DashLine)
    gap_pen.setCosmetic(True)

    prev = points[0] if points else None
    for group in groups:
        if group["silent"]:
            continue
        here = to_scene(group["lon"], group["lat"])
        if prev is not None and here != prev:
            path = QPainterPath(prev)
            path.lineTo(here)
            item = QGraphicsPathItem(path)
            item.setPen(gap_pen if (group["gap_before"] or group["country_only"]) else pen)
            item.setZValue(5)
            scene.addItem(item)
            items.append(item)
        prev = here
        points.append(here)
        if not group["country_only"]:
            fit_points.append(here)

    origin_label = origin.get("label")
    origin_drawn = False
    markers: list[MarkerItem] = []
    real = [g for g in groups if not g["silent"]]
    for group in groups:
        hops = [h["hop"] for h in group["hops"]]
        tip = group_tooltip(group, origin_label)
        label = hop_range(group["hops"])
        if group["at_origin"] and not origin_drawn:
            marker = MarkerItem(label, palette.origin, palette, origin=True,
                                caption=_short(origin_label), tooltip=tip, size=size, hops=hops)
            origin_drawn = True
        else:
            caption = None
            if group["country_only"]:
                caption = place_label(group["hops"][0])
            elif real and group is real[-1] and destination_label:
                caption = destination_label
            color = palette.sources.get(group["source"], palette.sources["unresolved"])
            marker = MarkerItem(label, color, palette, caption=caption, tooltip=tip, size=size,
                                hollow=group["country_only"], silent=group["silent"], hops=hops)
        marker.order = group["hops"][0]["hop"] + (1000 if group["silent"] else 0)
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
    items.extend(markers)

    if not fit_points:
        fit_points = points
    if not fit_points:
        return QRectF(), items
    xs = [p.x() for p in fit_points]
    ys = [p.y() for p in fit_points]
    return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)), items


def markers_of(items: list) -> list:
    return [i for i in items if isinstance(i, MarkerItem)]


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
    markers = markers_of(markers)
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
    """The interactive map.

    The world is drawn once per theme; the route is a separate layer, replaced
    as hops arrive, so a trace in progress redraws only its own markers. The
    view keeps itself fitted to the hops placed so far until the user zooms or
    pans, and from then on leaves the view alone (Fit hands control back).
    """

    originPicked = Signal(float, float)
    markerClicked = Signal(list)       # hop numbers in the clicked marker
    backgroundClicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.route: dict | None = None
        self.origin_only: tuple | None = None
        self.destination: str | None = None
        self.route_rect = QRectF()
        self.items_: list = []
        self.markers: list = []
        self.selected_hops: set[int] = set()
        self.picking = False
        self.user_moved = False
        self._press_pos = None
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
        self.btn_fit = self._tool("Fit", "Fit the route, and keep following it", lambda: self.fit_route())
        self.btn_world = self._tool("World", "Show the whole world", lambda: self.reset_view())
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

    def _fill_legend(self, sources: list[str], extra: list[str] | None = None):
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
        for kind in extra or []:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(6)
            dot = QLabel()
            dot.setFixedSize(10, 10)
            color = (self.palette_.sources["ip-db"] if kind == "country"
                     else self.palette_.route_gap)
            style = "dashed" if kind == "silent" else "solid"
            dot.setStyleSheet(f"background: transparent; border: 2px {style} {color.name()};"
                              " border-radius: 5px;")
            line.addWidget(dot)
            line.addWidget(QLabel("Country only (centroid)" if kind == "country"
                                  else "Not placed (yet)"))
            line.addStretch(1)
            self.legend_layout.addWidget(row)
        # Children added to a visible widget are only shown on the next event
        # loop pass, so size the legend after showing them now, or it measures
        # itself empty (found with a live trace redrawing it once per hop).
        for i in range(self.legend_layout.count()):
            widget = self.legend_layout.itemAt(i).widget()
            if widget is not None:
                widget.show()
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
        """The world for the current theme, then the route layer on top."""
        self.palette_ = theme.current()
        self.setScene(build_scene(self.palette_))
        self._style_overlays()
        self.items_, self.markers = [], []
        self._draw_route_layer()

    def _clear_route_layer(self):
        scene = self.scene()
        for item in self.items_:
            leader = getattr(item, "leader", None)
            if leader is not None and leader.scene() is scene:
                scene.removeItem(leader)
            if item.scene() is scene:
                scene.removeItem(item)
        self.items_, self.markers = [], []

    def _draw_route_layer(self):
        self._clear_route_layer()
        self.route_rect = QRectF()
        if self.route is not None:
            self.route_rect, self.items_ = draw_route(self.scene(), self.route, self.palette_,
                                                      self.destination)
            hops = self.route.get("hops") or []
            used = [s for s in ("hoiho", "site-code", "ip-db", "local")
                    if any(h.get("source") == s for h in hops)]
            extra = []
            if any(is_country_only(h) for h in hops):
                extra.append("country")
            if any(g["silent"] for g in route_groups(self.route)):
                extra.append("silent")
            self._fill_legend(used, extra)
            self.legend.show()
        else:
            self.legend.hide()
            if self.origin_only is not None:
                lat, lon, label = self.origin_only
                fake = {"origin": {"lat": lat, "lon": lon, "label": label}, "hops": []}
                self.route_rect, self.items_ = draw_route(self.scene(), fake, self.palette_)
        self.markers = markers_of(self.items_)
        for marker in self.markers:
            marker.clicked.connect(self.markerClicked)
            marker.set_selected(bool(self.selected_hops & set(marker.hops)))
        self._place_overlays()

    def theme_changed(self):
        self._rebuild()
        self.follow()

    def set_route(self, route: dict | None, destination: str | None = None, *,
                  keep_view: bool = False):
        """Draw *route*. Fit to it unless *keep_view* or the user has moved the map."""
        self.route, self.destination = route, destination
        self.origin_only = None
        self._draw_route_layer()
        if keep_view:
            self.follow()
        else:
            self.user_moved = False
            self.fit_route()

    def follow(self):
        """Refit to the route so far, unless the user has taken over the view."""
        if self.user_moved:
            self._declutter()
        else:
            self.fit_route(user=False)

    def set_origin(self, lat: float, lon: float, label: str | None):
        self.route = None
        self.origin_only = (lat, lon, label)
        self.selected_hops = set()
        self._draw_route_layer()
        self.user_moved = False
        self.reset_view(user=False)

    def show_card(self, title: str, body: str):
        self.card_title.setText(title)
        self.card_body.setText(body)
        self.card.show()
        self._place_overlays()

    def hide_card(self):
        self.card.hide()

    # ---- selection
    def highlight(self, hops: list[int], center: bool = False):
        """Ring the markers holding *hops*; optionally centre the first of them."""
        self.selected_hops = set(hops)
        target = None
        for marker in self.markers:
            on = bool(self.selected_hops & set(marker.hops))
            marker.set_selected(on)
            if on and target is None:
                target = marker
        if center and target is not None:
            # Centring is not the user taking over the view; Fit still follows.
            moved = self.user_moved
            self.centerOn(target.pos())
            self.user_moved = moved
            self._declutter()

    # ---- navigation
    def zoom(self, factor: float, user: bool = True):
        current = self.transform().m11()
        floor = self.viewport().height() / (180 * SCALE)
        target = max(floor, min(current * factor, 400.0))
        self.scale(target / current, target / current)
        if user:
            self.user_moved = True
        self._declutter()

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120.0
        if steps:
            self.zoom(1.25 ** steps)

    def fit_route(self, user: bool = True):
        if user:
            self.user_moved = False
        if self.route_rect.isNull() and self.route is None:
            self.reset_view(user=False)
            return
        aspect = max(0.2, self.viewport().width() / max(1, self.viewport().height()))
        self.fitInView(padded(self.route_rect, aspect), Qt.KeepAspectRatio)
        self._declutter()

    def reset_view(self, user: bool = True):
        """The world, filling the pane: height-led, so a tall pane shows a
        region rather than a thin strip; the map repeats sideways anyway."""
        if user:
            self.user_moved = True
        center_lon = 0.0
        if not self.route_rect.isNull() or self.origin_only:
            center_lon = self.route_rect.center().x() / SCALE
        aspect = max(0.2, self.viewport().width() / max(1, self.viewport().height()))
        height = 140.0
        width = min(360.0 * 1.6, max(height * aspect, 120.0))
        rect = QRectF((center_lon - width / 2) * SCALE, -80 * SCALE, width * SCALE, height * SCALE)
        self.fitInView(rect, Qt.KeepAspectRatio)
        self._declutter()

    # ---- mouse: origin picking, drag detection, background click
    def mousePressEvent(self, event):
        if self.picking and event.button() == Qt.LeftButton:
            point = self.mapToScene(event.position().toPoint())
            lon = ((point.x() / SCALE + 180) % 360) - 180
            lat = max(-90.0, min(90.0, -point.y() / SCALE))
            self.originPicked.emit(round(lat, 2), round(lon, 2))
            return
        self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._press_pos is None:
            return
        moved = (event.position().toPoint() - self._press_pos).manhattanLength()
        self._press_pos = None
        if moved > 4:
            self.user_moved = True
            self._declutter()
        elif self.itemAt(event.position().toPoint()) is None or not isinstance(
                self.itemAt(event.position().toPoint()), MarkerItem):
            if not any(m.isUnderMouse() for m in self.markers):
                self.backgroundClicked.emit()


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
