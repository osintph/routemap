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

from PySide6.QtCore import QTimer

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath,
                           QPen, QPolygonF)
from PySide6.QtWidgets import (QFrame, QGraphicsItem, QGraphicsObject, QGraphicsPathItem,
                               QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QToolButton,
                               QVBoxLayout, QWidget)

from routemap.gui import arcs, geometry, navigation, theme
from routemap.gui.text import markup, plain

SCALE = 4.0           # scene units per degree
ATTRIBUTION_BASE = "Natural Earth · GeoNames"
ATTRIBUTION_DBIP = "IP Geolocation by DB-IP"


def uses_dbip(route: dict | None) -> bool:
    """True when DB-IP data is on screen: a placement or an ASN from it."""
    return any(h.get("ip_provider") == "dbip" or h.get("asn_source") == "dbip"
               for h in (route or {}).get("hops") or [])
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
    if hop.get("source") == "ip-db":
        # Which tier answered: the offline file, or RIPEstat because the file
        # is not installed (or did not know the address).
        short += " (DB-IP)" if hop.get("ip_provider") == "dbip" else " (RIPEstat, online)"
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
        self.diff_mark: str | None = None     # set by a comparison: "added", "moved", "rtt", ...
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
        self.font.setPixelSize(round(11.5 * size))
        self.font.setBold(True)
        self.caption_font = QFont()
        self.caption_font.setPixelSize(round(11.5 * size))
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
        if self.diff_mark and self.diff_mark != "silent":
            painter.setBrush(Qt.NoBrush)
            mark_pen = QPen(theme.diff_color(self.palette, self.diff_mark), 2.0 * self.size)
            mark_pen.setStyle(Qt.DotLine if self.diff_mark == "removed" else Qt.SolidLine)
            painter.setPen(mark_pen)
            g = 7 * self.size
            painter.drawRoundedRect(rect.adjusted(-g, -g, g, g), h / 2 + g, h / 2 + g)
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


def _world_paths(scale: str = "50m") -> tuple[QPainterPath, QPainterPath, QPainterPath]:
    world = geometry.world(scale)

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


_PATHS: dict = {}


def world_paths(scale: str = "50m"):
    if scale not in _PATHS:
        _PATHS[scale] = _world_paths(scale)
    return _PATHS[scale]


def web_zoom(pixels_per_degree: float) -> float:
    """The web-map zoom level with the same pixel density (zoom 0 is the world
    in 256 pixels), which is the scale Natural Earth's ``min_zoom`` is set in."""
    return math.log2(max(1e-6, pixels_per_degree * 360.0 / 256.0))


DETAIL_ZOOM = 3.2        # from here the 1:10m coastline and city labels show
LABEL_SLACK = 0.7        # show a place a little before its own min_zoom
MAX_LABELS = 70
MAX_WORLD_LABELS = 30     # zoomed out: only the largest places, so the route stays readable


def visible_places(rect_deg: tuple[float, float, float, float], zoom: float,
                   limit: int = MAX_LABELS) -> list[dict]:
    """Natural Earth places inside (lon0, lat0, lon1, lat1), largest first, that
    Natural Earth labels at *zoom*. Longitudes may run past 180 (the flat map
    repeats); each place is returned at the copy that falls inside."""
    lon0, lat0, lon1, lat1 = rect_deg
    out = []
    for place in geometry.places():
        if place["min_zoom"] > zoom + LABEL_SLACK:
            continue
        if not lat0 <= place["lat"] <= lat1:
            continue
        for k in (-360.0, 0.0, 360.0):
            lon = place["lon"] + k
            if lon0 <= lon <= lon1:
                out.append(dict(place, lon=lon))
                break
        if len(out) >= limit:
            break
    return out


def build_scene(palette: theme.Palette, scale: str = "50m") -> QGraphicsScene:
    scene = QGraphicsScene()
    scene.setBackgroundBrush(palette.ocean)
    scene.setSceneRect(QRectF(-540 * SCALE, -90 * SCALE, 1080 * SCALE, 180 * SCALE))
    scene.world_items = add_world(scene, palette, scale)
    return scene


def add_world(scene: QGraphicsScene, palette: theme.Palette, scale: str = "50m") -> list:
    """Land, lakes and borders at *scale*, three copies side by side."""
    land, lakes, borders = world_paths(scale)
    items = []
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
        items += [item, lake, line]
    return items


def draw_route(scene: QGraphicsScene, route: dict, palette: theme.Palette,
               destination_label: str | None = None, size: float = 1.0, *,
               quiet_ms: float = 15.0, hot_ms: float = 60.0, ghost: bool = False,
               marks: dict | None = None) -> tuple[QRectF, list]:
    """Add the route to *scene*. Returns (the rect to fit, the items added).

    The rect covers the origin and every city-level hop. Country-only hops and
    silent hops do not stretch it: a country centroid is not a place the packet
    is known to have been.

    Each segment is a great-circle arc, coloured by the RTT the step added:
    grey under *quiet_ms*, warming to the hot colour at *hot_ms*. A segment
    into a gap or a country-only hop is dashed. *ghost* draws the whole route
    faint (the earlier run in a comparison); *marks* maps hop numbers to a
    diff mark ("added", "moved", "rtt", ...) shown as a ring.
    """
    items: list = []
    origin = route.get("origin") or {}
    groups = route_groups(route)
    fit_points, points = [], []
    if origin.get("lat") is not None:
        start = to_scene(origin["lon"], origin["lat"])
        fit_points.append(start)
        points.append(start)

    steps = {st["to"]: st for st in arcs.segment_steps(groups, origin, quiet_ms, hot_ms)}
    prev_ll = (origin["lat"], origin["lon"]) if origin.get("lat") is not None else None
    for index, group in enumerate(groups):
        if group["silent"]:
            continue
        here = to_scene(group["lon"], group["lat"])
        if prev_ll is not None and (prev_ll[0], prev_ll[1]) != (group["lat"], group["lon"]):
            line = arcs.great_circle(prev_ll[0], prev_ll[1], group["lat"], group["lon"])
            path = QPainterPath(to_scene(line[0][1], line[0][0]))
            for lat, lon in line[1:-1]:
                path.lineTo(to_scene(lon, lat))
            # End exactly on the marker, which route_groups has unwrapped.
            path.lineTo(here)
            step = steps.get(index) or {"class": "unknown", "intensity": 0.0}
            dashed = group["gap_before"] or group["country_only"]
            color = theme.step_color(palette, step["class"], step["intensity"])
            if ghost:
                color = QColor(palette.route_gap)
                color.setAlpha(150)
            seg_pen = QPen(color, 1.6 if ghost else (2.4 if step["class"] in ("warm", "hot") else 2.0),
                           Qt.DashLine if (dashed or ghost) else Qt.SolidLine)
            seg_pen.setCosmetic(True)
            seg_pen.setCapStyle(Qt.RoundCap)
            item = QGraphicsPathItem(path)
            item.setPen(seg_pen)
            item.setZValue(4 if ghost else 5)
            item.setToolTip("" if step.get("step_ms") is None else
                            f"+{step['step_ms']:.0f} ms RTT on this step")
            scene.addItem(item)
            items.append(item)
        prev_ll = (group["lat"], group["lon"])
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
        if marks:
            mark = next((marks[h] for h in hops if h in marks), None)
            if mark:
                marker.diff_mark = mark
        if ghost:
            marker.setOpacity(0.45)
            marker.setZValue(marker.zValue() - 3)
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
        self.quiet_ms, self.hot_ms = 15.0, 60.0
        self.ghost: dict | None = None        # an earlier run, drawn faint under the route
        self.marks: dict | None = None        # hop -> diff mark, for the route
        self.detail_items: list = []          # the 1:10m world, built on first zoom-in
        self.ghost_markers: list = []
        self.label_items: list = []
        self._detail_timer = QTimer(self)
        self._detail_timer.setSingleShot(True)
        self._detail_timer.setInterval(80)
        self._detail_timer.timeout.connect(self._update_detail)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumSize(QSize(360, 240))
        # Keys (+, -, arrows, 0) work once the map has been clicked.
        self.setFocusPolicy(Qt.StrongFocus)
        # Pinch arrives as native gestures on macOS; make sure they reach us.
        self.viewport().setAttribute(Qt.WA_AcceptTouchEvents, True)
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

        self.attribution = plain(ATTRIBUTION_BASE, self)
        self.attribution.setObjectName("attribution")

        self.card = _Overlay(self)
        card = QVBoxLayout(self.card)
        card.setContentsMargins(22, 18, 22, 18)
        card.setSpacing(6)
        self.card_title = plain("", self.card)
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

    def _fill_legend(self, sources: list[str], extra: list[str] | None = None, rtt: bool = False):
        while self.legend_layout.count():
            item = self.legend_layout.takeAt(0)
            old = item.widget()
            if old is not None:
                # Hidden and detached now: deleteLater alone leaves the old
                # rows painted under the new ones when the legend is refilled
                # twice in one pass (a route, then its comparison).
                old.hide()
                old.setParent(None)
                old.deleteLater()
        title = markup("<b>Placed by</b>")
        self.legend_layout.addWidget(title)
        for source in sources:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(6)
            dot = plain()
            dot.setFixedSize(10, 10)
            color = self.palette_.sources[source]
            dot.setStyleSheet(f"background: {color.name()}; border-radius: 5px;")
            line.addWidget(dot)
            line.addWidget(plain(theme.SOURCE_LABELS[source]))
            line.addStretch(1)
            self.legend_layout.addWidget(row)
        for kind in extra or []:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(6)
            dot = plain()
            dot.setFixedSize(10, 10)
            color = (self.palette_.sources["ip-db"] if kind == "country"
                     else self.palette_.route_gap)
            style = "dashed" if kind == "silent" else "solid"
            dot.setStyleSheet(f"background: transparent; border: 2px {style} {color.name()};"
                              " border-radius: 5px;")
            line.addWidget(dot)
            line.addWidget(plain("Country only (centroid)" if kind == "country"
                                  else "Not placed (yet)"))
            line.addStretch(1)
            self.legend_layout.addWidget(row)
        if rtt:
            head = markup("<b>RTT added per step</b>")
            self.legend_layout.addWidget(head)
            q, hot = self.quiet_ms, self.hot_ms
            for color, text in ((self.palette_.route_quiet, f"under {q:.0f} ms"),
                                (theme.mix(self.palette_.route_warm, self.palette_.route_hot, 0.3),
                                 f"{q:.0f} to {hot:.0f} ms"),
                                (self.palette_.route_hot, f"{hot:.0f} ms or more")):
                row = QWidget()
                line = QHBoxLayout(row)
                line.setContentsMargins(0, 0, 0, 0)
                line.setSpacing(6)
                swatch = plain()
                swatch.setFixedSize(18, 4)
                swatch.setStyleSheet(f"background: {color.name()}; border-radius: 2px;")
                line.addWidget(swatch)
                line.addWidget(plain(text))
                line.addStretch(1)
                self.legend_layout.addWidget(row)
            dash = QWidget()
            line = QHBoxLayout(dash)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(6)
            swatch = plain("- - -")
            swatch.setFixedWidth(18)
            swatch.setStyleSheet(f"color: {self.palette_.route_gap.name()}; font-weight: 700;")
            line.addWidget(swatch)
            line.addWidget(plain("silent stretch or country only"))
            line.addStretch(1)
            self.legend_layout.addWidget(dash)
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
        self._detail_timer.start()

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
        self.detail_items, self.label_items = [], []
        self._style_overlays()
        self.items_, self.markers = [], []
        self._draw_route_layer()
        self._detail_timer.start()

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
        self.ghost_markers = []
        if self.route is not None:
            ghost_items = []
            if self.ghost is not None:
                ghost_rect, ghost_items = draw_route(self.scene(), self.ghost, self.palette_, None,
                                                     quiet_ms=self.quiet_ms, hot_ms=self.hot_ms,
                                                     ghost=True)
            self.route_rect, self.items_ = draw_route(self.scene(), self.route, self.palette_,
                                                      self.destination, quiet_ms=self.quiet_ms,
                                                      hot_ms=self.hot_ms, marks=self.marks)
            if self.ghost is not None:
                self.route_rect = self.route_rect.united(ghost_rect) if not ghost_rect.isNull() \
                    else self.route_rect
                self.ghost_markers = markers_of(ghost_items)
                for item in self.ghost_markers:
                    item.setAcceptHoverEvents(False)
                    item.setAcceptedMouseButtons(Qt.NoButton)
                self.items_ = ghost_items + self.items_
            hops = self.route.get("hops") or []
            used = [s for s in ("hoiho", "site-code", "ip-db", "local")
                    if any(h.get("source") == s for h in hops)]
            extra = []
            if any(is_country_only(h) for h in hops):
                extra.append("country")
            if any(g["silent"] for g in route_groups(self.route)):
                extra.append("silent")
            self._fill_legend(used, extra, rtt=any(h.get("min_rtt_ms") is not None for h in hops))
            self.legend.show()
        else:
            self.legend.hide()
            if self.origin_only is not None:
                lat, lon, label = self.origin_only
                fake = {"origin": {"lat": lat, "lon": lon, "label": label}, "hops": []}
                self.route_rect, self.items_ = draw_route(self.scene(), fake, self.palette_)
        self.attribution.setText(ATTRIBUTION_BASE + (f" · {ATTRIBUTION_DBIP}" if uses_dbip(self.route)
                                                     else ""))
        ghosts = set(self.ghost_markers)
        self.markers = [m for m in markers_of(self.items_) if m not in ghosts]
        for marker in self.markers:
            marker.clicked.connect(self.markerClicked)
            marker.set_selected(bool(self.selected_hops & set(marker.hops)))
        self._place_overlays()

    def _update_detail(self):
        """1:10m land when zoomed in, 1:50m otherwise; city labels at every zoom,
        each place from the zoom Natural Earth gives it (capitals at world zoom).
        Labels used to start only past DETAIL_ZOOM, so whether a route showed
        any depended on the window's size (4 Oct 2026: shown on a Mac, not on a
        smaller Windows window)."""
        scene = self.scene()
        if scene is None:
            return
        zoom = web_zoom(self.transform().m11() * SCALE)
        detailed = zoom >= DETAIL_ZOOM
        if detailed and not self.detail_items:
            self.detail_items = add_world(scene, self.palette_, "10m")
            for item in self.detail_items:
                item.setZValue(0.5)
        for item in getattr(scene, "world_items", []):
            item.setVisible(not detailed)
        for item in self.detail_items:
            item.setVisible(detailed)
        for item in self.label_items:
            if item.scene() is scene:
                scene.removeItem(item)
        self.label_items = []
        rect = self.mapToScene(self.viewport().rect()).boundingRect()
        box = (rect.left() / SCALE, -rect.bottom() / SCALE, rect.right() / SCALE, -rect.top() / SCALE)
        font = QFont()
        font.setPixelSize(11)
        metrics = QFontMetricsF(font)
        taken = [QRectF(QPointF(self.mapFromScene(m.pos())) + m.offset - QPointF(m.w / 2 + 6, m.h / 2 + 6),
                        QSize(int(m.w + 12), int(m.h + 12))) for m in self.markers]
        color = self.palette_.overlay_muted
        for place in visible_places(box, zoom, limit=MAX_LABELS if detailed else MAX_WORLD_LABELS):
            point = QPointF(self.mapFromScene(to_scene(place["lon"], place["lat"])))
            w = metrics.horizontalAdvance(place["name"]) + 8
            area = QRectF(point.x() + 3, point.y() - metrics.height() / 2, w, metrics.height())
            if any(area.intersects(t) for t in taken):
                continue
            taken.append(area)
            text = scene.addSimpleText(place["name"], font)
            text.setBrush(color)
            text.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            text.setPos(to_scene(place["lon"], place["lat"]))
            text.setZValue(3)
            dot = scene.addEllipse(-1.6, -1.6, 3.2, 3.2, QPen(Qt.NoPen), QBrush(color))
            dot.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            dot.setPos(to_scene(place["lon"], place["lat"]))
            dot.setZValue(3)
            text.setTransform(text.transform().translate(4, -metrics.height() / 2))
            self.label_items += [text, dot]

    def set_thresholds(self, quiet_ms: float, hot_ms: float):
        if (quiet_ms, hot_ms) != (self.quiet_ms, self.hot_ms):
            self.quiet_ms, self.hot_ms = quiet_ms, hot_ms
            self._draw_route_layer()

    def set_comparison(self, ghost: dict | None, marks: dict | None):
        """Draw *ghost* (an earlier run) faint under the route, and ring the
        route's markers by *marks*. None, None ends the comparison."""
        self.ghost, self.marks = ghost, marks
        self._draw_route_layer()

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
    def zoom(self, factor: float, user: bool = True, at=None):
        """Zoom by *factor* within the limits, keeping the scene point under
        *at* (view pixels; default the centre) where it is."""
        vp = self.viewport()
        current = self.transform().m11()
        applied = navigation.zoom_factor(current, factor, vp.width(), vp.height())
        if abs(applied - 1.0) > 1e-9:
            pos = at if at is not None else QPointF(vp.rect().center())
            pos = pos.toPoint() if hasattr(pos, "toPoint") else pos
            before = self.mapToScene(pos)
            anchor = self.transformationAnchor()
            self.setTransformationAnchor(QGraphicsView.NoAnchor)
            self.scale(applied, applied)
            self.setTransformationAnchor(anchor)
            after = self.mapToScene(pos)
            centre = self.mapToScene(vp.rect().center())
            self.centerOn(centre + (before - after))
        if user:
            self.user_moved = True
        self._declutter()

    def pan(self, dx: float, dy: float):
        """Move the view by (dx, dy) view pixels; the scene rect clamps it, so
        the world cannot be dragged off screen."""
        h, v = self.horizontalScrollBar(), self.verticalScrollBar()
        h.setValue(int(round(h.value() - dx)))
        v.setValue(int(round(v.value() - dy)))
        self.user_moved = True
        self._declutter()

    def wheelEvent(self, event):
        from PySide6.QtGui import QInputDevice
        device = event.device()
        touchpad = (device is not None and device.type() == QInputDevice.DeviceType.TouchPad) \
            or event.phase() != Qt.NoScrollPhase
        mods = event.modifiers()
        action = navigation.wheel_action(
            event.angleDelta().x(), event.angleDelta().y(), event.pixelDelta().x(),
            event.pixelDelta().y(), touchpad=touchpad,
            zoom_modifier=bool(mods & (Qt.ControlModifier | Qt.MetaModifier)))
        if action[0] == "zoom":
            self.zoom(action[1], at=event.position())
        elif action[0] == "pan":
            self.pan(action[1], action[2])
        event.accept()       # never let a wheel over the map reach anything else

    def viewportEvent(self, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.NativeGesture:
            kind = event.gestureType()
            if kind == Qt.ZoomNativeGesture:
                self.zoom(navigation.gesture_factor(event.value()), at=event.position())
            elif kind == Qt.SmartZoomNativeGesture:
                self.zoom(navigation.DOUBLE_CLICK_ZOOM, at=event.position())
            event.accept()
            return True
        return super().viewportEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.picking:
            return
        if event.button() == Qt.LeftButton:
            self.zoom(navigation.DOUBLE_CLICK_ZOOM, at=event.position())
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        step = navigation.KEY_PAN_PX
        if key in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom(navigation.BUTTON_ZOOM)
        elif key in (Qt.Key_Minus, Qt.Key_Underscore):
            self.zoom(1 / navigation.BUTTON_ZOOM)
        elif key == Qt.Key_0:
            self.fit_route()
        elif key == Qt.Key_Left:
            self.pan(step, 0)
        elif key == Qt.Key_Right:
            self.pan(-step, 0)
        elif key == Qt.Key_Up:
            self.pan(0, step)
        elif key == Qt.Key_Down:
            self.pan(0, -step)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def fit_route(self, user: bool = True):
        if user:
            self.user_moved = False
        if self.route_rect.isNull() and self.route is None:
            self.reset_view(user=False)
            return
        vp = self.viewport()
        target = navigation.fit_scale(self.route_rect.width(), self.route_rect.height(),
                                      vp.width(), vp.height())
        current = self.transform().m11()
        if current > 0:
            anchor = self.transformationAnchor()
            self.setTransformationAnchor(QGraphicsView.NoAnchor)
            self.scale(target / current, target / current)
            self.setTransformationAnchor(anchor)
        self.centerOn(self.route_rect.center())
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
               title: str = "", provenance: str = "", destination: str | None = None,
               quiet_ms: float = 15.0, hot_ms: float = 60.0, ghost: dict | None = None,
               marks: dict | None = None) -> QImage:
    """The full route extent rendered off-screen, with legend and provenance.
    *ghost* and *marks* draw a comparison, as on screen."""
    palette = theme.DARK if dark else theme.LIGHT
    scene = build_scene(palette)
    markers = []
    rect = QRectF()
    if ghost is not None:
        rect, ghost_items = draw_route(scene, ghost, palette, None, size=1.35, quiet_ms=quiet_ms,
                                       hot_ms=hot_ms, ghost=True)
    main_rect, items = draw_route(scene, route, palette, destination, size=1.35, quiet_ms=quiet_ms,
                                  hot_ms=hot_ms, marks=marks)
    rect = main_rect if rect.isNull() else rect.united(main_rect)
    markers = markers_of(items)
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

    from routemap.gui.globeview import paint_legend
    paint_legend(painter, QPointF(24, height - 24), palette, route, quiet_ms, hot_ms, size=1.35)

    # Title top left, provenance bottom right.
    if title:
        tfont = QFont()
        tfont.setPixelSize(27)
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
        pfont.setPixelSize(15)
        painter.setFont(pfont)
        pm = QFontMetricsF(pfont)
        pw = pm.horizontalAdvance(provenance)
        painter.setPen(palette.overlay_muted)
        painter.drawText(QPointF(width - pw - 24, height - 20), provenance)
    painter.end()
    return image
