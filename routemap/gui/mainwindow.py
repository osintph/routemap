"""
The main window. Thin: it shows what the engine produced and nothing more.

Layout: the target field and Trace button on top; below, a splitter with the map
on the left and, on the right, the hop table (or the tool's live output while a
trace runs) over the collapsible unplaced-hops list; a history panel that can be
docked on the left; a status bar with the origin, the tool in use and per-source
progress.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QProgressBar, QPushButton, QSplitter, QStackedWidget, QStatusBar,
                               QVBoxLayout, QWidget)

from routemap.__about__ import DISPLAY_NAME
from routemap.gui.hoptable import HopTable
from routemap.gui.mapview import MapView
from routemap.gui.panels import HistoryPanel, LiveOutput, SourceStatus, UnplacedPanel

ORIGIN_APPROX = "approximate; wrong on a VPN or exit node"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(DISPLAY_NAME)
        self.resize(1440, 900)
        self.setMinimumSize(QSize(900, 560))
        self.closing = None
        self._build()
        self._menus()
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: self._theme_changed())

    # ---------------------------------------------------------------- build ---
    def _build(self):
        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(10, 10, 10, 0)
        outer.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.target = QLineEdit(central)
        self.target.setPlaceholderText("Hostname or IP address to trace, e.g. heise.de")
        self.target.setClearButtonEnabled(True)
        self.target.setMinimumHeight(30)
        self.trace_button = QPushButton("Trace", central)
        self.trace_button.setDefault(True)
        self.trace_button.setMinimumWidth(96)
        self.trace_button.setMinimumHeight(30)
        self.target.returnPressed.connect(self.trace_button.click)
        bar.addWidget(self.target, 1)
        bar.addWidget(self.trace_button)
        outer.addLayout(bar)

        self.splitter = QSplitter(Qt.Horizontal, central)
        self.map = MapView(self.splitter)
        right = QWidget(self.splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        self.stack = QStackedWidget(right)
        self.table = HopTable(self.stack)
        self.live = LiveOutput(self.stack)
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.live)
        self.summary = QLabel(right)
        self.summary.setTextFormat(Qt.RichText)
        self.unplaced = UnplacedPanel(right)
        right_layout.addWidget(self.summary)
        right_layout.addWidget(self.stack, 1)
        right_layout.addWidget(self.unplaced)
        self.splitter.addWidget(self.map)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([740, 680])
        outer.addWidget(self.splitter, 1)
        self.setCentralWidget(central)

        self.history_dock = QDockWidget("History", self)
        self.history_dock.setObjectName("history")
        self.history_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.history = HistoryPanel(self.history_dock)
        self.history_dock.setWidget(self.history)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.history_dock)
        self.history_dock.hide()
        self.history_dock.setMinimumWidth(170)
        self.resizeDocks([self.history_dock], [210], Qt.Horizontal)

        status = QStatusBar(self)
        self.origin_label = QLabel(status)
        self.origin_label.setTextFormat(Qt.RichText)
        self.tool_label = QLabel(status)
        self.tool_label.setTextFormat(Qt.RichText)
        self.busy = QProgressBar(status)
        self.busy.setRange(0, 0)
        self.busy.setMaximumWidth(90)
        self.busy.setMaximumHeight(12)
        self.busy.setTextVisible(False)
        self.busy.hide()
        self.sources = SourceStatus(status)
        status.addWidget(self.origin_label, 1)
        status.addPermanentWidget(self.tool_label)
        status.addPermanentWidget(self.busy)
        status.addPermanentWidget(self.sources)
        self.setStatusBar(status)

    def _menus(self):
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        self.act_open = QAction("Open Trace…", self, shortcut=QKeySequence.Open)
        self.act_paste = QAction("Paste Trace…", self, shortcut=QKeySequence("Ctrl+Shift+V"))
        self.act_export = QAction("Export…", self, shortcut=QKeySequence("Ctrl+E"))
        self.act_quit = QAction("Quit", self, shortcut=QKeySequence.Quit)
        self.act_quit.setMenuRole(QAction.QuitRole)
        for action in (self.act_open, self.act_paste, None, self.act_export, None, self.act_quit):
            file_menu.addSeparator() if action is None else file_menu.addAction(action)

        edit_menu = bar.addMenu("&Edit")
        self.act_copy = QAction("Copy Hop Table", self, shortcut=QKeySequence("Ctrl+Shift+C"))
        self.act_copy.triggered.connect(self.table.copy_selection)
        self.act_settings = QAction("Settings…", self, shortcut=QKeySequence("Ctrl+,"))
        self.act_settings.setMenuRole(QAction.PreferencesRole)
        edit_menu.addAction(self.act_copy)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_settings)

        view_menu = bar.addMenu("&View")
        view_menu.addAction(self.history_dock.toggleViewAction())
        fit = QAction("Fit Route", self, shortcut=QKeySequence("Ctrl+0"))
        fit.triggered.connect(self.map.fit_route)
        world = QAction("Whole World", self, shortcut=QKeySequence("Ctrl+9"))
        world.triggered.connect(self.map.reset_view)
        view_menu.addAction(fit)
        view_menu.addAction(world)

        trace_menu = bar.addMenu("&Trace")
        self.act_trace = QAction("Trace", self)
        self.act_trace.triggered.connect(self.trace_button.click)
        self.act_stop = QAction("Stop", self, shortcut=QKeySequence("Ctrl+."))
        self.act_atlas = QAction("Trace from a RIPE Atlas Probe…", self)
        trace_menu.addAction(self.act_trace)
        trace_menu.addAction(self.act_stop)
        trace_menu.addSeparator()
        trace_menu.addAction(self.act_atlas)

        help_menu = bar.addMenu("&Help")
        self.act_privacy = QAction("Privacy", self)
        self.act_update = QAction("Check for Updates…", self)
        self.act_about = QAction(f"About {DISPLAY_NAME}", self)
        self.act_about.setMenuRole(QAction.AboutRole)
        for action in (self.act_privacy, self.act_update, self.act_about):
            help_menu.addAction(action)

    def closeEvent(self, event):
        if callable(self.closing):
            self.closing()
        super().closeEvent(event)

    def _theme_changed(self):
        self.map.theme_changed()
        self.table.set_hops(self.table.model_.hops)

    # --------------------------------------------------------------- status ---
    def set_origin_status(self, label: str, how: str):
        """*how*: "ip" (from the public IP), "city", "coords" or "map"."""
        note = {"ip": f" <span style='color:gray'>(from your public IP, {ORIGIN_APPROX})</span>",
                "city": " <span style='color:gray'>(set in Settings)</span>",
                "coords": " <span style='color:gray'>(coordinates set in Settings)</span>",
                "map": " <span style='color:gray'>(picked on the map)</span>"}.get(how, "")
        self.origin_label.setText(f"<b>Origin</b> {label}{note}")

    def set_tool_status(self, argv: list[str] | None, missing_hint: str | None = None):
        if missing_hint:
            self.tool_label.setText("<span style='color:#c0392b'><b>No trace tool</b></span>")
            return
        if argv:
            import os
            parts = [os.path.basename(argv[0])] + list(argv[1:])
            shown = " ".join(parts[:-1] if len(parts) > 1 else parts)
            self.tool_label.setText(f"<code>{shown}</code>")

    # ---------------------------------------------------------------- states ---
    def show_idle(self, origin: tuple[float, float, str] | None, tool_hint: str | None = None):
        self.setWindowTitle(DISPLAY_NAME)
        self.trace_button.setText("Trace")
        self.busy.hide()
        self.sources.hide()
        self.stack.setCurrentWidget(self.table)
        self.table.set_hops([])
        self.unplaced.set_hops([])
        self.summary.setText("<span style='color:gray'>No route yet.</span>")
        if origin:
            self.map.set_origin(*origin)
        if tool_hint:
            self.map.show_card("No traceroute tool found", tool_hint)
            self.trace_button.setEnabled(False)
        else:
            self.map.show_card(
                "Trace a route from this machine",
                "Type a hostname or IP address above and press <b>Enter</b>. The trace runs "
                "here with your system's own tool, so the map starts where you are.<br><br>"
                "Traced somewhere else? <b>File › Paste Trace</b> or <b>Open Trace</b>.")
            self.trace_button.setEnabled(True)

    def show_tracing(self, target: str, argv: list[str], lines: list[str], hop_note: str):
        self.setWindowTitle(f"{target} - {DISPLAY_NAME}")
        self.target.setText(target)
        self.trace_button.setText("Stop")
        self.busy.show()
        self.sources.show()
        self.sources.reset()
        self.sources.set_state("trace", "started", hop_note)
        self.stack.setCurrentWidget(self.live)
        self.live.start(argv)
        for line in lines:
            self.live.append(line)
        self.summary.setText(f"<b>Tracing {target}</b> <span style='color:gray'>"
                             f"· output appears as the tool prints it</span>")
        self.unplaced.set_hops([])
        self.map.hide_card()
        self.set_tool_status(argv)

    def show_result(self, route: dict, target: str, argv: list[str] | None,
                    expand_unplaced: bool = False):
        hops = route.get("hops") or []
        placed = sum(1 for h in hops if h.get("lat") is not None)
        self.setWindowTitle(f"{target} - {DISPLAY_NAME}")
        self.target.setText(target)
        self.trace_button.setText("Trace")
        self.trace_button.setEnabled(True)
        self.busy.hide()
        self.sources.show()
        self.sources.finish()
        self.stack.setCurrentWidget(self.table)
        self.table.set_hops(hops)
        self.unplaced.set_hops(hops)
        self.unplaced.expand(expand_unplaced)
        self.map.hide_card()
        self.map.set_route(route, destination=target)
        warnings = "".join(f"<br><span style='color:#b7791f'>{w}</span>"
                           for w in route.get("warnings") or [])
        self.summary.setText(
            f"<b>{len(hops)} hops</b>, {placed} placed on the map "
            f"<span style='color:gray'>· {route.get('parser_label', '')}"
            f"{' · Hoiho ruleset ' + route['hoiho_ruleset_date'] if route.get('hoiho_ruleset_date') else ''}"
            f"</span>{warnings}")
        if argv:
            self.set_tool_status(argv)
