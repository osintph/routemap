"""
The map pane: the flat map and the globe behind one interface, a projection
switch, and Replay.

The window talks to this pane exactly as it used to talk to the flat map.
Every route, origin, selection and comparison goes to both views, so switching
projection never loses state; only the visible one is drawn.

Replay redraws the current route hop by hop over a few seconds, from the
origin outwards, then leaves the finished route in place. It changes nothing
but the drawing: the table, selection and exports are untouched.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QStackedLayout, QToolButton, QWidget

from routemap.gui.globeview import GlobeView
from routemap.gui.mapview import MapView, _Overlay

REPLAY_SECONDS = 4.0


class MapPane(QWidget):
    originPicked = Signal(float, float)
    markerClicked = Signal(list)
    backgroundClicked = Signal()
    projectionChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.flat = MapView(self)
        self.globe = GlobeView(self)
        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.flat)
        self.stack.addWidget(self.globe)
        self.projection = "flat"
        self.route: dict | None = None
        self.destination: str | None = None
        self._replay: list[dict] = []
        self._replay_timer = QTimer(self)
        self._replay_timer.timeout.connect(self._replay_step)
        for view in (self.flat, self.globe):
            view.markerClicked.connect(self.markerClicked)
            view.backgroundClicked.connect(self.backgroundClicked)
        self.flat.originPicked.connect(self.originPicked)
        self._build_switch()

    # ------------------------------------------------------------ switch ---
    def _build_switch(self):
        self.switch = _Overlay(self)
        row = QHBoxLayout(self.switch)
        row.setContentsMargins(4, 4, 4, 4)
        row.setSpacing(2)
        self.btn_flat = self._button("Flat", "Flat map (equirectangular)", lambda: self.set_projection("flat", user=True))
        self.btn_globe = self._button("Globe", "Globe, centred on the route; drag to turn it",
                                      lambda: self.set_projection("globe", user=True))
        self.btn_replay = self._button("Replay", "Draw the route again, hop by hop", self.replay)
        for b in (self.btn_flat, self.btn_globe):
            b.setCheckable(True)
        for b in (self.btn_flat, self.btn_globe, self.btn_replay):
            row.addWidget(b)
        self.btn_replay.setEnabled(False)
        self._style_switch()
        self._sync_switch()

    def _button(self, text, tip, slot):
        b = QToolButton(self.switch)
        b.setText(text)
        b.setToolTip(tip)
        b.setAutoRaise(True)
        b.clicked.connect(slot)
        return b

    def _style_switch(self):
        from routemap.gui import theme
        p = theme.current()
        bg = p.overlay_bg
        self.switch.setStyleSheet(
            f"#overlay {{ background: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()});"
            f" border: 1px solid {p.coast.name()}; border-radius: 8px; }}"
            f"#overlay QToolButton {{ color: {p.overlay_fg.name()}; font-weight: 600;"
            f" padding: 3px 9px; border-radius: 5px; }}"
            f"#overlay QToolButton:checked {{ background: {p.border.name()}; }}"
            f"#overlay QToolButton:disabled {{ color: {p.overlay_muted.name()}; }}")

    def _sync_switch(self):
        self.btn_flat.setChecked(self.projection == "flat")
        self.btn_globe.setChecked(self.projection == "globe")
        self.switch.adjustSize()
        self.switch.move(12, 12)
        self.switch.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_switch()

    def set_projection(self, projection: str, user: bool = False):
        if projection not in ("flat", "globe"):
            projection = "flat"
        if projection == "globe" and self.flat.picking:
            projection = "flat"           # the origin is picked on the flat map
        changed = projection != self.projection
        self.projection = projection
        self.stack.setCurrentWidget(self.globe if projection == "globe" else self.flat)
        self._sync_switch()
        if changed and user:
            self.projectionChanged.emit(projection)

    def current(self):
        return self.globe if self.projection == "globe" else self.flat

    # -------------------------------------------------- the old interface ---
    @property
    def picking(self) -> bool:
        return self.flat.picking

    @picking.setter
    def picking(self, on: bool):
        if on:
            self.set_projection("flat")
        self.flat.picking = on

    @property
    def markers(self):
        return self.flat.markers

    @property
    def legend(self):
        return self.flat.legend

    @property
    def card(self):
        return self.current().card

    @property
    def user_moved(self):
        return self.flat.user_moved

    def viewport(self):
        return self.flat.viewport()

    def transform(self):
        return self.flat.transform()

    def set_route(self, route, destination=None, *, keep_view: bool = False):
        self._stop_replay()
        self.route, self.destination = route, destination
        self.flat.set_route(route, destination, keep_view=keep_view)
        self.globe.set_route(route, destination, keep_view=keep_view)
        self.btn_replay.setEnabled(bool(route and (route.get("hops") or [])))

    def set_origin(self, lat, lon, label):
        self._stop_replay()
        self.route = None
        self.flat.set_origin(lat, lon, label)
        self.globe.set_origin(lat, lon, label)
        self.btn_replay.setEnabled(False)

    def set_thresholds(self, quiet_ms: float, hot_ms: float):
        self.flat.set_thresholds(quiet_ms, hot_ms)
        self.globe.set_thresholds(quiet_ms, hot_ms)

    def set_comparison(self, ghost, marks):
        self.flat.set_comparison(ghost, marks)
        self.globe.set_comparison(ghost, marks)

    def show_card(self, title, body):
        self.flat.show_card(title, body)
        self.globe.show_card(title, body)

    def hide_card(self):
        self.flat.hide_card()
        self.globe.hide_card()

    def highlight(self, hops, center=False):
        self.flat.highlight(hops, center)
        self.globe.highlight(hops, center)

    def fit_route(self, user: bool = True):
        self.current().fit_route(user)

    def reset_view(self, user: bool = True):
        self.current().reset_view(user)

    def zoom(self, factor: float, user: bool = True):
        self.current().zoom(factor, user)

    def theme_changed(self):
        self._style_switch()
        self.flat.theme_changed()
        self.globe.theme_changed()

    # ------------------------------------------------------------- replay ---
    def replay(self):
        if not self.route or not self.route.get("hops"):
            return
        hops = self.route["hops"]
        self._replay = [dict(self.route, hops=hops[:n]) for n in range(1, len(hops) + 1)]
        self._replay_timer.setInterval(max(60, int(REPLAY_SECONDS * 1000 / len(self._replay))))
        self.btn_replay.setEnabled(False)
        # The view stays where it is while the route grows: the flat map would
        # otherwise refit to every partial route.
        self._moved_before = self.flat.user_moved
        self.flat.user_moved = True
        view = self.current()
        view.set_route(dict(self.route, hops=[]), None, keep_view=True)
        self._replay_timer.start()

    def _replay_step(self):
        if not self._replay:
            self._stop_replay()
            return
        partial = self._replay.pop(0)
        last = not self._replay
        self.current().set_route(partial, self.destination if last else None, keep_view=True)
        if last:
            self._stop_replay()

    def _stop_replay(self):
        if self._replay_timer.isActive():
            self._replay_timer.stop()
            self._replay = []
            if self.route is not None:
                self.current().set_route(self.route, self.destination, keep_view=True)
            self.flat.user_moved = getattr(self, "_moved_before", self.flat.user_moved)
        self.btn_replay.setEnabled(bool(self.route and self.route.get("hops")))

    @property
    def replaying(self) -> bool:
        return self._replay_timer.isActive()
