"""
The main window. Thin: it shows what the engine produced and nothing more.

Layout: the target field, a small busy indicator and the Trace/Stop button on
top; below, a splitter with the map on the left and, on the right, the hop table
(growing live while a trace runs), the tool's own output collapsed beneath it,
and the unplaced hops. Nothing is ever laid over the map while tracing: state
is in the status bar. Selecting rows highlights their markers and selecting a
marker selects its rows; Esc clears both.
"""
from __future__ import annotations

import html
import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QDockWidget, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QProgressBar, QPushButton, QSplitter, QStatusBar, QVBoxLayout,
                               QWidget)

from routemap.__about__ import DISPLAY_NAME
from routemap.gui.hoptable import HopTable
from routemap.gui.insightpanel import HopDetails, InsightPanel
from routemap.gui.livepanel import ChangeList, LiveBar, PingPlot
from routemap.gui.mappane import MapPane
from routemap.gui.panels import HistoryPanel, LiveOutput, SourceStatus, UnplacedPanel
from routemap.gui.text import esc

ORIGIN_APPROX = "approximate; wrong on a VPN or exit node"


class MainWindow(QMainWindow):
    themeChosen = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(DISPLAY_NAME)
        self.resize(1440, 900)
        self.setMinimumSize(QSize(900, 560))
        self.closing = None
        self._build()
        self._menus()
        self._wire_selection()
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: self._os_scheme_changed())

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
        self.target.setAccessibleName("Target to trace")
        self.target.setAccessibleDescription("A host name or IP address. Press Enter or Trace to start.")
        self.target.setMinimumHeight(30)
        self.busy = QProgressBar(central)
        self.busy.setRange(0, 0)
        self.busy.setFixedWidth(64)
        self.busy.setMaximumHeight(8)
        self.busy.setTextVisible(False)
        self.busy.setToolTip("Tracing")
        self.busy.hide()
        self.trace_button = QPushButton("Trace", central)
        self.trace_button.setDefault(True)
        self.trace_button.setMinimumWidth(96)
        self.trace_button.setMinimumHeight(30)
        self.watch_button = QPushButton("Watch", central)
        self.watch_button.setToolTip("Trace continuously: every hop probed once a cycle, mtr style "
                                     "(Ctrl+Shift+W)")
        self.watch_button.setMinimumHeight(30)
        self.target.returnPressed.connect(self.trace_button.click)
        bar.addWidget(self.target, 1)
        bar.addWidget(self.busy, 0, Qt.AlignVCenter)
        bar.addWidget(self.trace_button)
        bar.addWidget(self.watch_button)
        outer.addLayout(bar)

        self.splitter = QSplitter(Qt.Horizontal, central)
        self.map = MapPane(self.splitter)
        for view, kind in ((self.map.flat, "Route map"), (self.map.globe, "Route globe")):
            view.setAccessibleName(kind)
            view.setAccessibleDescription("Arrow keys move between hops, Home and End go to the first hop "
                                          "and the destination, Enter selects, Esc clears; Shift with the "
                                          "arrows moves the view, plus and minus zoom, 0 fits the route.")
        right = QWidget(self.splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        self.summary = QLabel(right)
        self.summary.setTextFormat(Qt.RichText)
        self.summary.setWordWrap(True)
        self.right_split = QSplitter(Qt.Vertical, right)
        self.insight = InsightPanel(self.right_split)
        self.insight.setAccessibleName("Route summary")
        table_box = QWidget(self.right_split)
        table_layout = QVBoxLayout(table_box)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(6)
        self.live_bar = LiveBar(table_box)
        self.live_plot = PingPlot(table_box)
        self.live_changes = ChangeList(table_box)
        self.table = HopTable(table_box)
        self.table.setAccessibleName("Hop table")
        self.table.setAccessibleDescription("One row per hop. Arrow keys move between hops; the map follows.")
        self.details = HopDetails(table_box)
        table_layout.addWidget(self.live_bar)
        table_layout.addWidget(self.table, 1)
        table_layout.addWidget(self.live_plot)
        table_layout.addWidget(self.live_changes)
        table_layout.addWidget(self.details)
        for w in (self.live_bar, self.live_plot, self.live_changes):
            w.setVisible(False)
        self.right_split.addWidget(self.insight)
        self.right_split.addWidget(table_box)
        self.right_split.setStretchFactor(0, 2)
        self.right_split.setStretchFactor(1, 3)
        self.right_split.setSizes([300, 460])
        self.live = LiveOutput(right)
        self.unplaced = UnplacedPanel(right)
        right_layout.addWidget(self.summary)
        right_layout.addWidget(self.right_split, 1)
        right_layout.addWidget(self.live)
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
        self.state_label = QLabel(status)
        self.state_label.setTextFormat(Qt.RichText)
        self.tool_label = QLabel(status)
        self.tool_label.setTextFormat(Qt.RichText)
        self.sources = SourceStatus(status)
        status.addWidget(self.origin_label, 1)
        status.addPermanentWidget(self.state_label)
        status.addPermanentWidget(self.tool_label)
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
        self.act_copy.triggered.connect(lambda: self.table.copy_selection())
        self.act_settings = QAction("Settings…", self, shortcut=QKeySequence("Ctrl+,"))
        self.act_settings.setMenuRole(QAction.PreferencesRole)
        edit_menu.addAction(self.act_copy)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_settings)

        view_menu = bar.addMenu("&View")
        view_menu.addAction(self.history_dock.toggleViewAction())
        self.act_output = QAction("Tool Output", self, checkable=True)
        self.act_output.toggled.connect(self.live.toggle.setChecked)
        self.live.toggle.toggled.connect(self.act_output.setChecked)
        view_menu.addAction(self.act_output)
        fit = QAction("Fit Route", self, shortcut=QKeySequence("Ctrl+0"))
        fit.triggered.connect(lambda: self.map.fit_route())
        world = QAction("Whole World", self, shortcut=QKeySequence("Ctrl+9"))
        world.triggered.connect(lambda: self.map.reset_view())
        self.act_globe = QAction("Globe", self, checkable=True, shortcut=QKeySequence("Ctrl+G"))
        self.act_globe.toggled.connect(lambda on: self.map.set_projection("globe" if on else "flat", user=True))
        self.map.projectionChanged.connect(lambda proj: self.act_globe.setChecked(proj == "globe"))
        replay = QAction("Replay Route", self, shortcut=QKeySequence("Ctrl+R"))
        replay.triggered.connect(self.map.replay)
        from PySide6.QtGui import QActionGroup
        theme_menu = view_menu.addMenu("Theme")
        self.theme_group = QActionGroup(self)
        self.theme_actions = {}
        for key, label in (("system", "System"), ("light", "Light"), ("dark", "Dark")):
            act = QAction(label, self, checkable=True)
            act.triggered.connect(lambda _=False, k=key: self.themeChosen.emit(k))
            self.theme_group.addAction(act)
            theme_menu.addAction(act)
            self.theme_actions[key] = act
        self.theme_actions["system"].setChecked(True)
        view_menu.addSeparator()
        view_menu.addAction(self.act_globe)
        view_menu.addAction(replay)
        view_menu.addAction(fit)
        view_menu.addAction(world)

        trace_menu = bar.addMenu("&Trace")
        self.act_trace = QAction("Trace", self)
        self.act_trace.triggered.connect(self.trace_button.click)
        self.act_stop = QAction("Stop", self, shortcut=QKeySequence("Ctrl+."))
        self.act_watch = QAction("Watch Continuously", self, shortcut=QKeySequence("Ctrl+Shift+W"))
        self.act_reset_live = QAction("Reset Counters", self)
        self.act_reset_live.setEnabled(False)
        self.act_atlas = QAction("Trace from a RIPE Atlas Probe…", self)
        self.act_again = QAction("Trace Again and Compare", self, shortcut=QKeySequence("Ctrl+Shift+R"))
        self.act_compare_file = QAction("Compare with an Export…", self)
        self.act_compare_atlas = QAction("Compare with an Earlier Atlas Measurement…", self)
        self.act_end_compare = QAction("End Comparison", self)
        self.act_end_compare.setEnabled(False)
        trace_menu.addAction(self.act_trace)
        trace_menu.addAction(self.act_watch)
        trace_menu.addAction(self.act_stop)
        trace_menu.addAction(self.act_reset_live)
        trace_menu.addSeparator()
        trace_menu.addAction(self.act_again)
        trace_menu.addAction(self.act_compare_file)
        trace_menu.addAction(self.act_compare_atlas)
        trace_menu.addAction(self.act_end_compare)
        trace_menu.addSeparator()
        trace_menu.addAction(self.act_atlas)

        help_menu = bar.addMenu("&Help")
        self.act_privacy = QAction("Privacy", self)
        self.act_update = QAction("Check for Updates…", self)
        self.act_bug = QAction("Create Bug Report…", self)
        self.act_tour = QAction("Show the Tour", self)
        self.act_notices = QAction("Third-Party Notices", self)
        self.act_support = QAction(f"Support {DISPLAY_NAME}", self)
        self.act_about = QAction(f"About {DISPLAY_NAME}", self)
        self.act_about.setMenuRole(QAction.AboutRole)
        for action in (self.act_tour, self.act_privacy, self.act_notices, self.act_update, self.act_bug,
                       self.act_support, self.act_about):
            help_menu.addAction(action)

    # ------------------------------------------------------------ selection ---
    def _wire_selection(self):
        self.table.hopsSelected.connect(lambda hops: self.map.highlight(hops, center=bool(hops)))
        self.map.markerClicked.connect(self._marker_clicked)
        self.map.markerStepped.connect(lambda hops: self.table.select_hops(hops))
        self.map.backgroundClicked.connect(self.clear_selection)
        escape = QShortcut(QKeySequence(Qt.Key_Escape), self)
        escape.setContext(Qt.WindowShortcut)
        escape.activated.connect(self.clear_selection)

    def _marker_clicked(self, hops: list):
        self.table.select_hops(hops)
        self.map.highlight(hops, center=False)
        self.table.setFocus()

    def clear_selection(self):
        self.table.select_hops([], scroll=False)
        self.map.highlight([])

    def closeEvent(self, event):
        if callable(self.closing):
            self.closing()
        super().closeEvent(event)

    def sync_theme_menu(self, choice: str):
        act = self.theme_actions.get(choice)
        if act is not None:
            act.setChecked(True)

    def _os_scheme_changed(self):
        """The OS switched light/dark: follow it only when the theme is System."""
        from PySide6.QtWidgets import QApplication

        from routemap.gui import theme
        if theme.choice() == "system" and not getattr(self, "_reapplying", False):
            self._reapplying = True
            try:
                theme.apply(QApplication.instance(), "system")
            finally:
                self._reapplying = False
            self._theme_changed()

    def _theme_changed(self):
        self.map.theme_changed()
        m = self.table.model_
        self.table.set_hops(m.hops, m.details, m.marks)
        if callable(getattr(self, "refresh_panels", None)):
            self.refresh_panels()

    # --------------------------------------------------------------- status ---
    def set_origin_status(self, label: str, how: str):
        """*how*: "ip" (from the public IP), "city", "coords" or "map"."""
        note = {"ip": f" <span style='color:gray'>(from your public IP, {ORIGIN_APPROX})</span>",
                "city": " <span style='color:gray'>(set in Settings)</span>",
                "coords": " <span style='color:gray'>(coordinates set in Settings)</span>",
                "map": " <span style='color:gray'>(picked on the map)</span>"}.get(how, "")
        self.origin_label.setText(f"<b>Origin</b> {esc(label)}{note}")

    def set_tool_status(self, argv: list[str] | None, missing_hint: str | None = None):
        if missing_hint:
            self.tool_label.setText("<span style='color:#c0392b'><b>No trace tool</b></span>")
            return
        if argv:
            parts = [os.path.basename(argv[0])] + list(argv[1:])
            shown = " ".join(parts[:-1] if len(parts) > 1 else parts)
            self.tool_label.setText(f"<code>{html.escape(shown)}</code>")

    def set_state(self, text: str = ""):
        self.state_label.setText(text)

    def set_running(self, running: bool):
        self.busy.setVisible(running)
        self.trace_button.setText("Stop" if running else "Trace")

    # ---------------------------------------------------------------- states ---
    def show_idle(self, origin: tuple[float, float, str] | None, tool_hint: str | None = None):
        self.setWindowTitle(DISPLAY_NAME)
        self.set_running(False)
        self.set_state("")
        self.sources.hide()
        self.table.set_hops([])
        self.unplaced.set_hops([])
        self.insight.clear()
        self.details.hide()
        self.live.start([])
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

    def show_tracing(self, target: str, argv: list[str], lines: list[str] | None = None,
                     hop_note: str = "starting"):
        """A trace has started: empty table, live output armed, nothing over the map."""
        self.setWindowTitle(f"{target} - {DISPLAY_NAME}")
        self.target.setText(target)
        self.set_running(True)
        self.sources.show()
        self.sources.reset()
        self.sources.set_state("trace", "started", hop_note)
        self.map.hide_card()
        self.table.set_hops([])
        self.unplaced.set_hops([])
        self.insight.clear()
        self.details.hide()
        self.live.start(argv)
        for line in lines or []:
            self.live.append(line)
        self.summary.setText(f"<b>Tracing {esc(target)}</b>")
        self.set_state(f"Tracing <b>{esc(target)}</b>…")
        self.set_tool_status(argv)

    def update_live(self, route: dict, target: str, hop_note: str = ""):
        """Hops placed so far, drawn at once; the view follows unless the user moved it."""
        hops = route.get("hops") or []
        placed = sum(1 for h in hops if h.get("lat") is not None)
        self.table.set_hops(hops)
        self.unplaced.set_hops(hops)
        self.map.set_route(route, destination=None, keep_view=True)
        self.summary.setText(f"<b>Tracing {esc(target)}</b> <span style='color:gray'>· "
                             f"{len(hops)} hops so far, {placed} placed</span>")
        self.set_state(f"Tracing <b>{esc(target)}</b>: {esc(hop_note or f'hop {len(hops)}')}")

    # -------------------------------------------------------- continuous ---
    def set_live_mode(self, on: bool) -> None:
        """Show or hide the continuous-mode widgets and switch the table's columns."""
        self.table.set_live(on)
        for w in (self.live_bar, self.live_plot, self.live_changes):
            w.setVisible(on)
        self.live.setVisible(not on and self.live.isVisible())

    def show_watching(self, target: str) -> None:
        self.setWindowTitle(f"{target} (live) - {DISPLAY_NAME}")
        self.target.setText(target)
        self.set_live_mode(True)
        self.trace_button.setEnabled(False)
        self.watch_button.setEnabled(False)
        self.act_reset_live.setEnabled(True)
        self.map.hide_card()
        self.table.set_hops([])
        self.unplaced.set_hops([])
        self.insight.clear()
        self.details.hide()
        self.summary.setText(f"<b>Watching {esc(target)}</b> <span style='color:gray'>· the first cycle "
                             "finds the path</span>")
        self.set_state(f"Watching <b>{esc(target)}</b>")

    def update_watch(self, hops: list[dict], snap: dict, running: bool, details: dict | None = None) -> None:
        """One cycle's figures: the table, the plot, the changes and the bar."""
        self.table.set_hops(hops, details)
        selected = self.table.selected_hops()
        self.live_plot.set_data(snap, selected[0] if selected else None)
        self.live_changes.set_data(snap)
        self.live_bar.show_state(snap, running)
        loss = (snap.get("loss") or {}).get("text") or ""
        self.insight.set_loss(loss)
        placed = sum(1 for h in hops if h.get("lat") is not None)
        self.summary.setText(f"<b>{len(hops)} hops</b>, {placed} placed <span style='color:gray'>· "
                             f"{esc(loss)}</span>")

    def end_watch(self) -> None:
        self.trace_button.setEnabled(True)
        self.watch_button.setEnabled(True)
        self.act_reset_live.setEnabled(False)
        self.set_state("")

    def show_result(self, route: dict, target: str, argv: list[str] | None,
                    expand_unplaced: bool = False, trace_text: str | None = None,
                    keep_view: bool = False):
        hops = route.get("hops") or []
        placed = sum(1 for h in hops if h.get("lat") is not None)
        self.setWindowTitle(f"{target} - {DISPLAY_NAME}")
        self.target.setText(target)
        self.set_running(False)
        self.trace_button.setEnabled(True)
        self.set_state("")
        self.sources.show()
        self.sources.finish()
        self.map.hide_card()
        self.table.set_hops(hops)
        self.unplaced.set_hops(hops)
        self.unplaced.expand(expand_unplaced)
        if trace_text is not None:
            self.live.set_text(trace_text, argv)
        self.map.set_route(route, destination=target, keep_view=keep_view)
        # Every value from the route is escaped: a route can come from a file.
        warnings = "".join(f"<br><span style='color:#b7791f'>{html.escape(str(w))}</span>"
                           for w in route.get("warnings") or [])
        ruleset = route.get("hoiho_ruleset_date")
        detail = html.escape(str(route.get("parser_label") or ""))
        if ruleset:
            detail += f" · Hoiho ruleset {html.escape(str(ruleset))}"
        self.summary.setText(
            f"<b>{len(hops)} hops</b>, {placed} placed on the map "
            f"<span style='color:gray'>· {detail}</span>{warnings}")
        if argv:
            self.set_tool_status(argv)
