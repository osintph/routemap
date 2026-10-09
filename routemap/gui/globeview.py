"""
The globe: an orthographic view of the same route, centred on its midpoint,
dragged to rotate.

Why a second view at all: on a flat map a Manila to Frankfurt route bends
north for no visible reason; on a globe the same great circle is the obvious
shortest line. The globe draws the same groups, markers, colours and RTT steps
as the flat map (mapview.route_groups, arcs.segment_steps), so the two can
never disagree about the route.

Drawing is plain QPainter, re-projected on every frame. While the user drags,
the coastline is a coarser simplification of the 1:50m data, so rotation keeps
up on a slow machine; the full 1:50m is drawn as soon as the drag stops.
Points behind the globe are clamped to the horizon, which closes a land
polygon cut by the edge along the edge itself.
"""
from __future__ import annotations

import html
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QToolTip, QVBoxLayout, QWidget

from routemap.gui import arcs, geometry, navigation, theme
from routemap.gui.mapview import (ATTRIBUTION_BASE, ATTRIBUTION_DBIP, describe_hops, group_tooltip, hop_range,
                                  is_country_only, place_label, route_groups, step_index, uses_dbip, _short)
from routemap.gui.naturalearth import simplify
from routemap.gui.text import plain

COARSE_TOLERANCE_DEG = 0.6
MIN_ZOOM, MAX_ZOOM = 0.6, 12.0


class Ortho:
    """Orthographic projection onto a disc of radius *r* centred at (cx, cy)."""

    def __init__(self, lat0: float, lon0: float, cx: float, cy: float, r: float):
        self.lat0, self.lon0, self.cx, self.cy, self.r = lat0, lon0, cx, cy, r
        self.sin0, self.cos0 = math.sin(math.radians(lat0)), math.cos(math.radians(lat0))

    def project(self, lat: float, lon: float) -> tuple[float, float, bool]:
        """(x, y, visible). A hidden point comes back clamped to the horizon."""
        la, dl = math.radians(lat), math.radians(lon - self.lon0)
        cos_la = math.cos(la)
        x = cos_la * math.sin(dl)
        y = self.cos0 * math.sin(la) - self.sin0 * cos_la * math.cos(dl)
        z = self.sin0 * math.sin(la) + self.cos0 * cos_la * math.cos(dl)
        if z < 0:
            n = math.hypot(x, y) or 1.0
            x, y = x / n, y / n
        return self.cx + self.r * x, self.cy - self.r * y, z >= 0

    def invert(self, px: float, py: float) -> tuple[float, float] | None:
        x, y = (px - self.cx) / self.r, (self.cy - py) / self.r
        rho = math.hypot(x, y)
        if rho > 1:
            return None
        c = math.asin(min(1.0, rho))
        if rho < 1e-12:
            return self.lat0, self.lon0
        lat = math.asin(math.cos(c) * self.sin0 + y * math.sin(c) * self.cos0 / rho)
        lon = self.lon0 + math.degrees(math.atan2(x * math.sin(c),
                                                  rho * self.cos0 * math.cos(c) - y * self.sin0 * math.sin(c)))
        return math.degrees(lat), ((lon + 180) % 360) - 180


_COARSE = None


def _coarse_world() -> dict:
    global _COARSE
    if _COARSE is None:
        world = geometry.world("50m")
        _COARSE = {k: [r2 for r2 in (simplify(list(r), COARSE_TOLERANCE_DEG) for r in world[k])
                       if len(r2) >= (2 if k == "borders" else 4)]
                   for k in ("land", "lakes", "borders")}
    return _COARSE


class GlobeView(QWidget):
    markerClicked = Signal(list)
    markerStepped = Signal(list)       # chosen with the keyboard: focus stays here
    backgroundClicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.route: dict | None = None
        self.destination: str | None = None
        self.origin_only: tuple | None = None
        self.ghost: dict | None = None
        self.marks: dict | None = None
        self.selected_hops: set[int] = set()
        self.quiet_ms, self.hot_ms = 15.0, 60.0
        self.center = (15.0, 100.0)
        self.zoom_ = 1.0
        self.dragging = False
        self._press = None
        self._press_center = None
        self._hits: list[tuple[QRectF, list[int], str]] = []
        self.setMouseTracking(True)
        self.setMinimumSize(QSize(360, 240))
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(140)
        self._settle.timeout.connect(self._settled)
        self._build_overlays()

    # ---------------------------------------------------------- overlays ---
    def _build_overlays(self):
        from routemap.gui.mapview import _Overlay
        self.controls = _Overlay(self)
        box = QVBoxLayout(self.controls)
        box.setContentsMargins(4, 4, 4, 4)
        box.setSpacing(2)
        for text, tip, slot in (("+", "Zoom in", lambda: self.zoom(1.4)),
                                ("−", "Zoom out", lambda: self.zoom(1 / 1.4)),
                                ("Fit", "Centre on the route", lambda: self.fit_route()),
                                ("World", "The whole globe", lambda: self.reset_view())):
            button = QToolButton(self.controls)
            button.setText(text)
            button.setToolTip(tip)
            button.setAutoRaise(True)
            button.setMinimumWidth(46)
            button.clicked.connect(slot)
            box.addWidget(button)
        self.attribution = plain(ATTRIBUTION_BASE, self)
        self.attribution.setObjectName("attribution")
        self.card = _Overlay(self)
        card = QVBoxLayout(self.card)
        card.setContentsMargins(22, 18, 22, 18)
        self.card_title = plain("", self.card)
        self.card_title.setObjectName("cardTitle")
        self.card_body = QLabel(self.card)
        self.card_body.setWordWrap(True)
        self.card_body.setObjectName("cardBody")
        self.card_body.setTextFormat(Qt.RichText)
        card.addWidget(self.card_title)
        card.addWidget(self.card_body)
        self.card.hide()
        self._style()

    def _style(self):
        p = theme.current()
        bg = p.overlay_bg
        css = (f"#overlay {{ background: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()});"
               f" border: 1px solid {p.coast.name()}; border-radius: 8px; }}"
               f"#overlay QToolButton {{ color: {p.overlay_fg.name()}; font-weight: 600;"
               f" padding: 3px 6px; border-radius: 5px; }}"
               f"#overlay QToolButton:hover {{ background: {p.border.name()}; }}"
               f"#overlay QLabel {{ color: {p.overlay_fg.name()}; background: transparent; }}"
               f"#cardTitle {{ font-size: 16px; font-weight: 600; }}"
               f"#cardBody {{ color: {p.overlay_muted.name()}; }}"
               f"#attribution {{ color: {p.overlay_muted.name()}; background: transparent; font-size: 10px; }}")
        for widget in (self.controls, self.card, self.attribution):
            widget.setStyleSheet(css)

    def _place_overlays(self):
        m = 12
        self.controls.adjustSize()
        self.controls.move(self.width() - self.controls.width() - m, m)
        self.attribution.adjustSize()
        self.attribution.move(self.width() - self.attribution.width() - m,
                              self.height() - self.attribution.height() - 6)
        self.card.setFixedWidth(min(440, self.width() - 2 * m))
        self.card.adjustSize()
        self.card.move((self.width() - self.card.width()) // 2,
                       min(self.height() - self.card.height() - 56, int(self.height() * 0.58)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_overlays()

    def show_card(self, title: str, body: str):
        self.card_title.setText(title)
        self.card_body.setText(body)
        self.card.show()
        self._place_overlays()

    def hide_card(self):
        self.card.hide()

    # ------------------------------------------------------------- content ---
    def theme_changed(self):
        self._style()
        self.update()

    def set_thresholds(self, quiet_ms: float, hot_ms: float):
        self.quiet_ms, self.hot_ms = quiet_ms, hot_ms
        self.update()

    def set_route(self, route: dict | None, destination: str | None = None, *, keep_view: bool = False):
        self.route, self.destination, self.origin_only = route, destination, None
        self.attribution.setText(ATTRIBUTION_BASE + (f" · {ATTRIBUTION_DBIP}" if uses_dbip(route) else ""))
        if not keep_view:
            self.fit_route()
        self.update()

    def set_origin(self, lat: float, lon: float, label: str | None):
        self.route, self.origin_only = None, (lat, lon, label)
        self.selected_hops = set()
        self.center, self.zoom_ = (lat, lon), 1.0
        self.update()

    def set_comparison(self, ghost: dict | None, marks: dict | None):
        self.ghost, self.marks = ghost, marks
        self.update()

    def highlight(self, hops: list[int], center: bool = False):
        self.selected_hops = set(hops)
        if center and self.route:
            for group in route_groups(self.route):
                if set(h["hop"] for h in group["hops"]) & self.selected_hops and not group["silent"]:
                    self.center = (group["lat"], group["lon"])
                    break
        self.update()

    def _points(self) -> list[tuple[float, float]]:
        pts = []
        for route in (self.route, self.ghost):
            if not route:
                continue
            origin = route.get("origin") or {}
            if origin.get("lat") is not None:
                pts.append((origin["lat"], origin["lon"]))
            pts += [(g["lat"], g["lon"]) for g in route_groups(route) if not g["country_only"]
                    and not g["silent"]]
        return pts

    def fit_route(self, user: bool = True):
        pts = self._points()
        if not pts:
            self.reset_view()
            return
        self.center = arcs.midpoint(pts)
        lat0, lon0 = self.center
        # Zoom so the farthest point from the centre sits inside the disc.
        far = max(math.degrees(math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(
            arcs._vec(lat0, lon0), arcs._vec(la, lo))))))) for la, lo in pts)
        self.zoom_ = max(MIN_ZOOM, min(MAX_ZOOM, 0.92 / max(0.18, math.sin(math.radians(min(far + 6, 90))))))
        self.update()

    def reset_view(self, user: bool = True):
        self.zoom_ = 1.0
        pts = self._points()
        if pts:
            self.center = arcs.midpoint(pts)
        self.update()

    def zoom(self, factor: float, user: bool = True):
        self.zoom_ = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom_ * factor))
        self.update()

    # --------------------------------------------------------------- paint ---
    def _proj(self) -> Ortho:
        r = min(self.width(), self.height()) * 0.44 * self.zoom_
        return Ortho(self.center[0], self.center[1], self.width() / 2, self.height() / 2, r)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.paint_into(p, QRectF(self.rect()), theme.current(), coarse=self.dragging)
        p.end()

    def paint_into(self, p: QPainter, rect: QRectF, pal: theme.Palette, *, coarse: bool = False,
                   size: float = 1.0):
        """Draw the globe and the route into *rect*. Also used for exports."""
        r = min(rect.width(), rect.height()) * 0.44 * self.zoom_
        proj = Ortho(self.center[0], self.center[1], rect.center().x(), rect.center().y(), r)
        p.fillRect(rect, pal.space)
        disc = QPainterPath()
        disc.addEllipse(QPointF(proj.cx, proj.cy), r, r)
        p.setPen(Qt.NoPen)
        p.setBrush(pal.ocean)
        p.drawPath(disc)
        p.save()
        p.setClipPath(disc)
        world = _coarse_world() if coarse else geometry.world("50m")
        land = QPainterPath()
        land.setFillRule(Qt.WindingFill)
        for ring in world["land"]:
            self._ring(land, proj, ring)
        p.setBrush(pal.land)
        p.setPen(QPen(pal.coast, 0.8))
        p.drawPath(land)
        lakes = QPainterPath()
        for ring in world["lakes"]:
            self._ring(lakes, proj, ring)
        p.setBrush(pal.ocean)
        p.drawPath(lakes)
        borders = QPainterPath()
        for line in world["borders"]:
            self._line(borders, proj, line)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(pal.border, 0.7))
        p.drawPath(borders)
        self._graticule(p, proj, pal)
        self._hits = []
        if self.ghost is not None:
            self._draw_route(p, proj, self.ghost, pal, ghost=True, size=size)
        if self.route is not None:
            self._draw_route(p, proj, self.route, pal, size=size)
        elif self.origin_only is not None:
            lat, lon, label = self.origin_only
            x, y, vis = proj.project(lat, lon)
            if vis:
                self._pill(p, QPointF(x, y), "", pal.origin, pal, origin=True, caption=_short(label),
                           size=size)
        p.restore()
        p.setPen(QPen(pal.coast, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(proj.cx, proj.cy), r, r)
        if self.route is not None:
            paint_legend(p, QPointF(rect.left() + 12, rect.bottom() - 12), pal, self.route,
                         self.quiet_ms, self.hot_ms, size=size)

    @staticmethod
    def _ring(path: QPainterPath, proj: Ortho, ring) -> None:
        pts = [proj.project(lat, lon) for lon, lat in ring]
        if not any(v for _, _, v in pts):
            return
        path.moveTo(pts[0][0], pts[0][1])
        for x, y, _ in pts[1:]:
            path.lineTo(x, y)
        path.closeSubpath()

    @staticmethod
    def _line(path: QPainterPath, proj: Ortho, line) -> None:
        drawing = False
        for lon, lat in line:
            x, y, vis = proj.project(lat, lon)
            if not vis:
                drawing = False
                continue
            if drawing:
                path.lineTo(x, y)
            else:
                path.moveTo(x, y)
                drawing = True

    def _graticule(self, p: QPainter, proj: Ortho, pal: theme.Palette):
        pen = QPen(pal.coast, 0.5)
        color = QColor(pal.coast)
        color.setAlpha(90)
        pen.setColor(color)
        p.setPen(pen)
        path = QPainterPath()
        for lon in range(-180, 180, 30):
            self._line(path, proj, [(lon, lat) for lat in range(-90, 91, 3)])
        for lat in range(-60, 61, 30):
            self._line(path, proj, [(lon, lat) for lon in range(-180, 181, 3)])
        p.drawPath(path)

    def _draw_route(self, p: QPainter, proj: Ortho, route: dict, pal: theme.Palette, *,
                    ghost: bool = False, size: float = 1.0):
        origin = route.get("origin") or {}
        groups = route_groups(route)
        steps = {st["to"]: st for st in arcs.segment_steps(groups, origin, self.quiet_ms, self.hot_ms)}
        prev = (origin["lat"], origin["lon"]) if origin.get("lat") is not None else None
        for i, group in enumerate(groups):
            if group["silent"]:
                continue
            here = (group["lat"], group["lon"])
            if prev is not None and prev != here:
                step = steps.get(i) or {"class": "unknown", "intensity": 0.0}
                color = theme.step_color(pal, step["class"], step["intensity"])
                if ghost:
                    color = QColor(pal.route_gap)
                    color.setAlpha(150)
                pen = QPen(color, (1.6 if ghost else (2.6 if step["class"] in ("warm", "hot") else 2.1)) * size)
                pen.setCapStyle(Qt.RoundCap)
                if group["gap_before"] or group["country_only"] or ghost:
                    pen.setStyle(Qt.DashLine)
                elif pal.hot_dashed and step["class"] == "hot":
                    pen.setStyle(Qt.DashDotLine)   # as on the flat map: hot not by colour alone
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                path = QPainterPath()
                self._line(path, proj, [(lon, lat) for lat, lon in arcs.great_circle(*prev, *here)])
                p.drawPath(path)
            prev = here
        origin_drawn = False
        real = [g for g in groups if not g["silent"]]
        for group in groups:
            x, y, vis = proj.project(group["lat"], group["lon"])
            if not vis:
                continue
            hops = [h["hop"] for h in group["hops"]]
            label = hop_range(group["hops"])
            if group["at_origin"] and not origin_drawn:
                color, origin_flag, caption = pal.origin, True, _short(origin.get("label"))
                origin_drawn = True
            else:
                color = pal.sources.get(group["source"], pal.sources["unresolved"])
                origin_flag = False
                caption = place_label(group["hops"][0]) if group["country_only"] else (
                    self.destination if (real and group is real[-1] and self.destination and not ghost) else None)
            mark = None
            if self.marks and not ghost:
                mark = next((self.marks[h] for h in hops if h in self.marks), None)
            rect = self._pill(p, QPointF(x, y), label, color, pal, origin=origin_flag, caption=caption,
                              hollow=group["country_only"], silent=group["silent"],
                              selected=bool(self.selected_hops & set(hops)) and not ghost,
                              ghost=ghost, mark=mark, size=size)
            if not ghost:
                self._hits.append((rect, hops, group_tooltip(group, origin.get("label"))))
        if origin.get("lat") is not None and not origin_drawn:
            x, y, vis = proj.project(origin["lat"], origin["lon"])
            if vis:
                self._pill(p, QPointF(x, y), "", pal.origin, pal, origin=True,
                           caption=_short(origin.get("label")), ghost=ghost, size=size)

    def _pill(self, p: QPainter, at: QPointF, label: str, color: QColor, pal: theme.Palette, *,
              origin=False, caption=None, hollow=False, silent=False, selected=False, ghost=False,
              mark=None, size: float = 1.0) -> QRectF:
        font = QFont()
        font.setPixelSize(round(11.5 * size))
        font.setBold(True)
        metrics = QFontMetricsF(font)
        h = (20.0 if label else 14.0) * size
        w = max(h, metrics.horizontalAdvance(label) + 12 * size) if label else h
        rect = QRectF(at.x() - w / 2, at.y() - h / 2, w, h)
        p.save()
        if ghost:
            p.setOpacity(0.45)
        if origin:
            p.setPen(QPen(pal.origin, 2.0))
            p.setBrush(pal.marker_ring)
            p.drawRoundedRect(rect, h / 2, h / 2)
            if label:
                p.setFont(font)
                p.drawText(rect, Qt.AlignCenter, label)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(pal.origin)
                p.drawEllipse(at, 3.5, 3.5)
        elif hollow or silent:
            outline = pal.route_gap if silent else color
            pen = QPen(outline, 2.0 * size)
            if silent:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(pal.overlay_bg)
            p.drawRoundedRect(rect, h / 2, h / 2)
            p.setFont(font)
            p.drawText(rect, Qt.AlignCenter, label)
        else:
            p.setPen(QPen(pal.marker_ring, 2.0))
            p.setBrush(color)
            p.drawRoundedRect(rect, h / 2, h / 2)
            p.setFont(font)
            p.setPen(pal.marker_text)
            p.drawText(rect, Qt.AlignCenter, label)
        if mark and mark != "silent":
            g = 7 * size
            pen = QPen(theme.diff_color(pal, mark), 2.0 * size)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(-g, -g, g, g), h / 2 + g, h / 2 + g)
        if selected:
            g = 4 * size
            p.setPen(QPen(pal.route, 2.5 * size))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(-g, -g, g, g), h / 2 + g, h / 2 + g)
        if caption:
            cfont = QFont()
            cfont.setPixelSize(round(11.5 * size))
            cm = QFontMetricsF(cfont)
            cw = cm.horizontalAdvance(caption) + 12
            crect = QRectF(at.x() - cw / 2, rect.bottom() + 3, cw, cm.height() + 4)
            p.setPen(Qt.NoPen)
            p.setBrush(pal.overlay_bg)
            p.drawRoundedRect(crect, 4, 4)
            p.setFont(cfont)
            p.setPen(pal.overlay_fg)
            p.drawText(crect, Qt.AlignCenter, caption)
        p.restore()
        return rect

    # --------------------------------------------------------------- mouse ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = event.position()
            self._press_center = self.center

    def mouseMoveEvent(self, event):
        if self._press is not None:
            d = event.position() - self._press
            if not self.dragging and d.manhattanLength() > 4:
                self.dragging = True
            if self.dragging:
                r = min(self.width(), self.height()) * 0.44 * self.zoom_
                lat = self._press_center[0] + math.degrees(d.y() / r)
                lon = self._press_center[1] - math.degrees(d.x() / r)
                self.center = (max(-85.0, min(85.0, lat)), ((lon + 180) % 360) - 180)
                self.update()
            return
        hit = self._hit(event.position())
        if hit:
            QToolTip.showText(event.globalPosition().toPoint(), hit[2], self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, event):
        if self._press is None:
            return
        was_drag = self.dragging
        self._press = None
        if was_drag:
            self._settle.start()
            return
        hit = self._hit(event.position())
        if hit:
            self.markerClicked.emit(hit[1])
        else:
            self.backgroundClicked.emit()

    def _settled(self):
        self.dragging = False
        self.update()

    def rotate_by(self, dx: float, dy: float):
        """Turn the globe as if dragged by (dx, dy) pixels."""
        r = min(self.width(), self.height()) * 0.44 * self.zoom_
        lat = self.center[0] + math.degrees(dy / r)
        lon = self.center[1] - math.degrees(dx / r)
        self.center = (max(-85.0, min(85.0, lat)), ((lon + 180) % 360) - 180)
        self.dragging = True
        self._settle.start()
        self.update()

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
            self.zoom(action[1])
        elif action[0] == "pan":
            self.rotate_by(action[1], action[2])
        event.accept()

    def event(self, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.NativeGesture:
            kind = event.gestureType()
            if kind == Qt.ZoomNativeGesture:
                self.zoom(navigation.gesture_factor(event.value()))
            elif kind == Qt.SmartZoomNativeGesture:
                self.zoom(navigation.DOUBLE_CLICK_ZOOM)
            event.accept()
            return True
        return super().event(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and not self._hit(event.position()):
            self.zoom(navigation.DOUBLE_CLICK_ZOOM)
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
        elif event.modifiers() & Qt.ShiftModifier and key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            self.rotate_by(*{Qt.Key_Left: (step, 0), Qt.Key_Right: (-step, 0),
                             Qt.Key_Up: (0, step), Qt.Key_Down: (0, -step)}[key])
        elif key in (Qt.Key_Left, Qt.Key_Up, Qt.Key_Right, Qt.Key_Down, Qt.Key_Home, Qt.Key_End):
            delta, absolute = {Qt.Key_Left: (-1, False), Qt.Key_Up: (-1, False), Qt.Key_Right: (1, False),
                               Qt.Key_Down: (1, False), Qt.Key_Home: (0, True), Qt.Key_End: (-1, True)}[key]
            self.step_marker(delta, absolute)
        elif key in (Qt.Key_Return, Qt.Key_Enter) and self.selected_hops:
            self.markerClicked.emit(sorted(self.selected_hops))
        elif key == Qt.Key_Escape:
            self.highlight([])
            self.backgroundClicked.emit()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def step_marker(self, delta: int, absolute: bool = False) -> None:
        groups = [[h["hop"] for h in g["hops"]] for g in route_groups(self.route or {}) if not g["silent"]] \
            if self.route else []
        index = step_index(groups, self.selected_hops, delta, absolute)
        if index is None:
            return
        self.highlight(groups[index], center=True)
        self.setAccessibleDescription(describe_hops(self.route, groups[index], index, len(groups)))
        self.markerStepped.emit(groups[index])

    def _hit(self, pos: QPointF):
        for rect, hops, tip in reversed(self._hits):
            if rect.adjusted(-3, -3, 3, 3).contains(pos):
                return rect, hops, tip
        return None


def _legend_rows(route: dict, pal: theme.Palette, quiet_ms: float, hot_ms: float) -> list:
    """The rows both legends show, in order: (kind, value)."""
    from routemap.gui.mapview import route_groups
    hops = route.get("hops") or []
    used = [s for s in ("hoiho", "site-code", "ip-db", "local") if any(h.get("source") == s for h in hops)]
    rows: list[tuple[str, object]] = [("title", "Placed by")]
    rows += [("dot", s) for s in used]
    if any(h.get("precision") == "country" for h in hops):
        rows.append(("ring", (pal.sources["ip-db"], "Country only (centroid)")))
    if any(g["silent"] for g in route_groups(route)):
        rows.append(("ring", (pal.route_gap, "Not placed (yet)")))
    if any(h.get("min_rtt_ms") is not None for h in hops):
        rows.append(("title", "RTT added per step"))
        rows += [("line", (pal.route_quiet, f"under {quiet_ms:.0f} ms")),
                 ("line", (theme.mix(pal.route_warm, pal.route_hot, 0.3), f"{quiet_ms:.0f} to {hot_ms:.0f} ms")),
                 ("line", (pal.route_hot, f"{hot_ms:.0f} ms or more"
                                          + (", dash-dot line" if pal.hot_dashed else ""))),
                 ("dash", (pal.route_gap, "silent stretch or country only"))]
    return rows


def legend_rows(route: dict, pal: theme.Palette, quiet_ms: float, hot_ms: float) -> list[tuple[str, str]]:
    """(kind, text) for each legend row: what both legends say, for comparisons."""
    return [(k, theme.SOURCE_LABELS[v] if k == "dot" else (v if k == "title" else v[1]))
            for k, v in _legend_rows(route, pal, quiet_ms, hot_ms)]


def paint_legend(p: QPainter, bottom_left: QPointF, pal: theme.Palette, route: dict,
                 quiet_ms: float, hot_ms: float, size: float = 1.0) -> QRectF:
    """The flat map's legend, painted: sources used, then the RTT step colours."""
    rows = _legend_rows(route, pal, quiet_ms, hot_ms)
    font = QFont()
    font.setPixelSize(round(12 * size))
    bold = QFont(font)
    bold.setBold(True)
    m = QFontMetricsF(font)
    line_h = m.height() + 3 * size
    texts = [theme.SOURCE_LABELS[v] if k == "dot" else (v if k == "title" else v[1]) for k, v in rows]
    width = max(m.horizontalAdvance(t) for t in texts) + 44 * size
    height = line_h * len(rows) + 16 * size
    box = QRectF(bottom_left.x(), bottom_left.y() - height, width, height)
    p.save()
    p.setPen(QPen(pal.coast, 1))
    p.setBrush(pal.overlay_bg)
    p.drawRoundedRect(box, 8, 8)
    y = box.top() + 8 * size
    for kind, value in rows:
        mid = y + m.height() / 2
        x = box.left() + 10 * size
        if kind == "title":
            p.setFont(bold)
            p.setPen(pal.overlay_fg)
            p.drawText(QPointF(x, y + m.ascent()), value)
        else:
            if kind == "dot":
                p.setPen(Qt.NoPen)
                p.setBrush(pal.sources[value])
                p.drawEllipse(QPointF(x + 5 * size, mid), 5 * size, 5 * size)
                label = theme.SOURCE_LABELS[value]
            elif kind == "ring":
                color, label = value
                p.setPen(QPen(color, 2 * size))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(x + 5 * size, mid), 4.5 * size, 4.5 * size)
            else:
                color, label = value
                pen = QPen(color, 3 * size if kind == "line" else 2 * size)
                if kind == "dash":
                    pen.setStyle(Qt.DashLine)
                p.setPen(pen)
                p.drawLine(QPointF(x, mid), QPointF(x + 16 * size, mid))
            p.setFont(font)
            p.setPen(pal.overlay_fg)
            p.drawText(QPointF(x + 24 * size, y + m.ascent()), label)
        y += line_h
    p.restore()
    return box
