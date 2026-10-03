"""
The running desktop app: the main window wired to the engine.

Owns the settings, the current route and the background jobs. Every button and
menu item lands in a method here; every slow thing runs in a workers.Task; the
window classes only display what they are given.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
import sys

from PySide6.QtCore import QByteArray, QObject, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from routemap import config, service
from routemap.__about__ import DISPLAY_NAME, NAME, REPO_URL, __version__
from routemap.engine import (InvalidTarget, Route, SqliteCache, TraceParseError, analyse, atlas,
                             available_tools, install_hint, validate_target, whereami)
from routemap.engine.runner import TraceToolMissing, pick_tool
from routemap.gui import dialogs, mapview, report
from routemap.gui.mainwindow import MainWindow
from routemap.gui.workers import Task

LOCAL, PASTE, FILE, ATLAS = "local", "paste", "file", "atlas"


class Controller(QObject):
    def __init__(self, window: MainWindow, settings: config.Settings):
        super().__init__(window)
        self.w = window
        self.settings = settings
        self.tools = available_tools()
        self.origin: tuple[float, float, str] | None = None
        self.origin_how: str | None = None
        self.origin_task: Task | None = None
        self.task: Task | None = None
        self.current: dict | None = None      # {"route", "target", "trace_text", "argv", "source", ...}
        self.history: list[dict] = []
        self.picking_from: dialogs.SettingsDialog | None = None
        self._wire()

    # ------------------------------------------------------------- wiring ---
    def _wire(self):
        w = self.w
        w.trace_button.clicked.connect(self.trace_or_stop)
        w.act_stop.triggered.connect(self.stop)
        w.act_open.triggered.connect(self.open_file)
        w.act_paste.triggered.connect(self.paste)
        w.act_export.triggered.connect(self.export)
        w.act_settings.triggered.connect(lambda: self.open_settings())
        w.act_quit.triggered.connect(w.close)
        w.act_atlas.triggered.connect(self.atlas_trace)
        w.act_privacy.triggered.connect(lambda: dialogs.PrivacyDialog(w).exec())
        w.act_update.triggered.connect(self.check_update)
        w.act_about.triggered.connect(self.about)
        w.history.opened.connect(self.open_history)
        w.history.cleared.connect(self.clear_history)
        w.map.originPicked.connect(self._picked)
        w.closing = self.save_window

    def start(self):
        if self.settings.window_geometry:
            try:
                self.w.restoreGeometry(QByteArray.fromBase64(self.settings.window_geometry.encode()))
            except Exception:  # noqa: BLE001
                pass
        self.refresh_history()
        self._refresh_tool_status()
        self._refresh_atlas_action()
        chosen = self.settings.origin()
        if chosen is not None:
            self.origin, self.origin_how = chosen, self.settings.origin_mode
        self.show_idle()
        if self.origin is None:
            self.lookup_origin()

    # --------------------------------------------------------------- state ---
    def show_idle(self):
        hint = None if self.tools else _no_tool_html()
        self.w.show_idle(self.origin, tool_hint=hint)
        self._refresh_origin_status()

    def _refresh_origin_status(self):
        if self.origin:
            self.w.set_origin_status(self.origin[2], self.origin_how or "")
        elif self.origin_task is not None and self.origin_task.isRunning():
            self.w.origin_label.setText("<b>Origin</b> <span style='color:gray'>finding this "
                                        "machine's approximate location…</span>")
        else:
            self.w.origin_label.setText(
                "<b>Origin</b> <span style='color:#c0392b'>unknown</span> <span style='color:gray'>"
                "(set one in Settings › Origin; routes start at the first located hop "
                "until then)</span>")

    def _refresh_tool_status(self):
        try:
            tool, path = pick_tool(self.settings.tool)
            self.w.set_tool_status([tool, *self.settings.flags_for(tool), "x"])
        except (TraceToolMissing, ValueError):
            self.w.set_tool_status(None, missing_hint=install_hint())

    def _refresh_atlas_action(self):
        s = self.settings
        self.w.act_atlas.setEnabled(bool(s.atlas_enabled and s.atlas_key))
        self.w.act_atlas.setToolTip("" if s.atlas_enabled and s.atlas_key
                                    else "Turn on RIPE Atlas and add your key in Settings")

    def busy(self) -> bool:
        return self.task is not None and self.task.isRunning()

    def error(self, title: str, text: str):
        box = QMessageBox(QMessageBox.Warning, title, text, QMessageBox.Ok, self.w)
        box.setTextFormat(Qt.PlainText)
        box.exec()

    # -------------------------------------------------------------- origin ---
    def lookup_origin(self):
        def job(on_line, on_progress, cancel):
            return asyncio.run(whereami.locate_me(user_agent=service.user_agent()))

        task = Task(job, self)
        task.succeeded.connect(self._origin_found)
        task.failed.connect(self._origin_failed)
        self.origin_task = task
        task.start()
        self._refresh_origin_status()

    def _origin_found(self, me: dict):
        if self.settings.origin() is not None:
            return
        self.origin, self.origin_how = (me["lat"], me["lon"], me["label"]), service.ORIGIN_HOW_IP
        self._refresh_origin_status()
        if self.current is None and not self.busy():
            self.w.map.set_origin(*self.origin)

    def _origin_failed(self, message: str):
        self._refresh_origin_status()
        self.w.statusBar().showMessage(f"Could not find this machine's location: {message}", 8000)

    # --------------------------------------------------------------- trace ---
    def trace_or_stop(self):
        if self.busy():
            self.stop()
        else:
            self.trace()

    def stop(self):
        if self.busy():
            self.task.stop()
            self.w.statusBar().showMessage("Stopping…", 3000)

    def trace(self):
        raw = self.w.target.text()
        try:
            target = validate_target(raw)
        except InvalidTarget as exc:
            self.w.summary.setText(f"<span style='color:#c0392b'>{exc}.</span>")
            self.w.target.setFocus()
            return
        try:
            tool, _path = pick_tool(self.settings.tool)
        except (TraceToolMissing, ValueError) as exc:
            self.error("No trace tool", str(exc))
            return
        settings = self.settings
        origin = self.origin

        def job(on_line, on_progress, cancel):
            result = service.run(target, settings, cancel=cancel, on_line=on_line)
            if result.cancelled:
                raise RuntimeError("Stopped.")
            if not result.text.strip():
                raise RuntimeError(f"{result.tool} printed nothing (exit code {result.returncode}).")
            on_progress("trace", "done")
            route = asyncio.run(analyse(result.text, origin[:2] if origin else None,
                                        sources=service.sources_for(settings),
                                        progress=lambda s, st, d: on_progress(s, st, d)))
            return {"route": route, "text": result.text, "argv": result.argv,
                    "timed_out": result.timed_out}

        from routemap.engine.runner import build_argv
        argv = build_argv(tool, tool, target, settings.flags_for(tool))
        self.w.show_tracing(target, argv, [], "starting")
        if not origin:
            self.w.map.show_card(f"Tracing {target}", "Hops are placed when the trace finishes.")
        else:
            self.w.map.set_origin(*origin)
            self.w.map.show_card(f"Tracing {target}", "Hops are placed when the trace finishes. "
                                                      "The tool's own output is on the right as it arrives.")
        self._run(job, target=target, source=LOCAL)

    def _run(self, job, *, target: str, source: str):
        task = Task(job, self)
        task.line.connect(self._line)
        task.progress.connect(lambda s, st, d: self.w.sources.set_state(s, st, d or None))
        task.succeeded.connect(lambda r: self._done(r, target, source))
        task.failed.connect(self._failed)
        self.task = task
        self.w.trace_button.setText("Stop")
        self.w.busy.show()
        task.start()

    def _line(self, line: str):
        self.w.live.append(line)
        stripped = line.strip()
        number = stripped.split()[0].rstrip(".|-") if stripped else ""
        if number.isdigit():
            self.w.sources.set_state("trace", "started", f"hop {number}")

    def _done(self, result: dict, target: str, source: str):
        route: Route = result["route"]
        body = route.to_dict()
        self.current = {"route": body, "target": target, "trace_text": result["text"],
                        "argv": result.get("argv"), "source": source,
                        "origin_how": result.get("origin_how") or (
                            self.origin_how if body["origin"]["source"] == "supplied" else "first-hop"),
                        "when": _dt.datetime.now().astimezone()}
        self.w.show_result(body, target, result.get("argv"))
        self.w.busy.hide()
        if result.get("timed_out"):
            self.w.statusBar().showMessage("The trace hit its time limit; the hops it reached "
                                           "are shown.", 10000)
        entry = config.history_entry(body, target=target, trace_text=result["text"],
                                     argv=result.get("argv"), source=source)
        entry["origin_how"] = self.current["origin_how"]
        config.add_history(entry, self.settings)
        self.refresh_history()

    def _failed(self, message: str):
        self.w.busy.hide()
        self.w.trace_button.setText("Trace")
        self.w.sources.hide()
        if self.current:
            c = self.current
            self.w.show_result(c["route"], c["target"], c.get("argv"))
        else:
            self.show_idle()
        self.w.summary.setText(f"<span style='color:#c0392b'>{_html(message)}</span>")

    # ----------------------------------------------------- paste and open ---
    def paste(self, text: str = ""):
        clip = text or ""
        if not clip:
            candidate = QGuiApplication.clipboard().text() or ""
            if "ms" in candidate and len(candidate.splitlines()) > 1:
                clip = candidate
        dialog = dialogs.PasteTraceDialog(self.w, text=clip,
                                          origin_label=self.origin[2] if self.origin else "")
        dialog.changeOrigin.connect(lambda: (self.open_settings(tab=0),
                                             dialog.set_origin_label(self.origin[2] if self.origin else "")))
        if dialog.exec():
            self.analyse_text(dialog.text(), "pasted trace", PASTE)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self.w, "Open a trace", os.path.expanduser("~"),
            "Traces and route exports (*.txt *.log *.json);;All files (*)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError as exc:
            self.error("Could not open the file", str(exc))
            return
        if path.lower().endswith(".json"):
            try:
                document = json.loads(text)
                route = document["route"]
                Route.from_dict(route)
            except (ValueError, KeyError, TypeError):
                self.error("Not a route export", "That JSON file is not a routemap export.")
                return
            trace = document.get("trace") or {}
            self.current = {"route": route, "target": document.get("target") or os.path.basename(path),
                            "trace_text": trace.get("text") or "", "argv": trace.get("argv"),
                            "source": trace.get("source") or FILE,
                            "origin_how": document.get("origin_how"), "when": _dt.datetime.now().astimezone()}
            self.w.show_result(route, self.current["target"], self.current["argv"])
            return
        self.analyse_text(text, os.path.basename(path), FILE)

    def analyse_text(self, text: str, label: str, source: str):
        if self.busy():
            return
        settings, origin = self.settings, self.origin

        def job(on_line, on_progress, cancel):
            route = asyncio.run(analyse(text, origin[:2] if origin else None,
                                        sources=service.sources_for(settings),
                                        progress=lambda s, st, d: on_progress(s, st, d)))
            return {"route": route, "text": text, "argv": None}

        try:
            from routemap.engine import parse_trace
            parsed = parse_trace(text)
        except TraceParseError as exc:
            self.error("Not a trace", str(exc))
            return
        target = parsed.target or label
        self.w.summary.setText(f"<b>Analysing {_html(target)}</b> <span style='color:gray'>"
                               f"· {len(parsed.hops)} hops</span>")
        self.w.sources.show()
        self.w.sources.reset()
        self.w.sources.set_state("trace", "off" if source != LOCAL else "done")
        self._run(job, target=target, source=source)

    # -------------------------------------------------------------- export ---
    def export(self):
        if not self.current:
            self.error("Nothing to export", "Trace a route, paste a trace or open one first.")
            return
        dialog = dialogs.ExportDialog(self.w, selected="pdf")
        if not dialog.exec():
            return
        fmt = dialog.selected()
        c = self.current
        stem = f"route-{c['target']}-{c['when'].strftime('%Y%m%d-%H%M')}".replace("/", "-")
        filters = {"png": "PNG image (*.png)", "pdf": "PDF report (*.pdf)", "json": "JSON (*.json)"}
        path, _ = QFileDialog.getSaveFileName(self.w, "Export", os.path.join(
            os.path.expanduser("~"), f"{stem}.{fmt}"), filters[fmt])
        if not path:
            return
        if not path.lower().endswith("." + fmt):
            path += "." + fmt
        try:
            write_export(fmt, path, c, dark_png=dialog.png_dark.isChecked(),
                         include_trace=dialog.appendix.isChecked())
        except Exception as exc:  # noqa: BLE001
            self.error("Export failed", str(exc))
            return
        self.w.statusBar().showMessage(f"Exported {os.path.basename(path)}", 6000)

    # ------------------------------------------------------------ settings ---
    def open_settings(self, tab: int = 0):
        cache_count = 0
        try:
            if os.path.exists(config.cache_path()):
                cache_count = len(SqliteCache(config.cache_path()))
        except Exception:  # noqa: BLE001
            pass
        dialog = dialogs.SettingsDialog(self.w, self.settings,
                                        origin_label=self.origin[2] if self.origin else "",
                                        tools=self.tools, cache_count=cache_count,
                                        history_count=len(config.load_history()))
        dialog.tabs.setCurrentIndex(tab)
        dialog.pickRequested.connect(lambda: self._start_pick(dialog))
        dialog.clearCacheRequested.connect(lambda: self._clear_cache(dialog))
        dialog.clearHistoryRequested.connect(lambda: self._clear_history(dialog))
        if not dialog.exec():
            return
        problems = dialog.values_into(self.settings)
        config.save_settings(self.settings)
        for problem in problems:
            self.error("Settings", problem)
        chosen = self.settings.origin()
        if chosen is not None:
            self.origin, self.origin_how = chosen, self.settings.origin_mode
        elif self.origin_how != service.ORIGIN_HOW_IP:
            self.origin, self.origin_how = None, None
            self.lookup_origin()
        self._refresh_origin_status()
        self._refresh_tool_status()
        self._refresh_atlas_action()
        self.refresh_history()
        if self.current is None and self.origin:
            self.w.map.set_origin(*self.origin)

    def _start_pick(self, dialog):
        self.picking_from = dialog
        dialog.hide()
        self.w.map.picking = True
        self.w.map.viewport().setCursor(Qt.CrossCursor)
        self.w.map.show_card("Click the map to set your origin",
                             "Zoom and pan as usual; the click sets the point. "
                             "It is stored to about a kilometre.")

    def _picked(self, lat: float, lon: float):
        self.w.map.picking = False
        self.w.map.viewport().unsetCursor()
        self.w.map.hide_card()
        if self.picking_from is not None:
            dialog, self.picking_from = self.picking_from, None
            dialog.set_picked(lat, lon)
            dialog.show()

    def _clear_cache(self, dialog):
        try:
            removed = SqliteCache(config.cache_path()).clear()
        except Exception as exc:  # noqa: BLE001
            self.error("Clear cache", str(exc))
            return
        dialog.clear_cache.setText(f"Cleared ({removed} hostnames)")
        dialog.clear_cache.setEnabled(False)

    def _clear_history(self, dialog=None):
        removed = config.clear_history()
        if dialog is not None:
            dialog.clear_history.setText(f"Cleared ({removed} traces)")
            dialog.clear_history.setEnabled(False)
        self.refresh_history()

    # ------------------------------------------------------------- history ---
    def refresh_history(self):
        self.history = config.load_history() if self.settings.history_enabled else []
        entries = [{"target": e["target"],
                    "when": _dt.datetime.fromtimestamp(e["when"]).strftime("%-d %b %H:%M")
                    if sys.platform != "win32" else
                    _dt.datetime.fromtimestamp(e["when"]).strftime("%d %b %H:%M"),
                    "hops": e.get("hops", 0), "placed": e.get("placed", 0),
                    "tool": service.tool_label(e.get("argv"))} for e in self.history]
        self.w.history.set_entries(entries, enabled=self.settings.history_enabled,
                                   limit=config.HISTORY_LIMIT)

    def open_history(self, row: int):
        if not 0 <= row < len(self.history):
            return
        e = self.history[row]
        self.current = {"route": e["route"], "target": e["target"], "trace_text": e.get("trace_text", ""),
                        "argv": e.get("argv"), "source": e.get("source", LOCAL),
                        "origin_how": e.get("origin_how"),
                        "when": _dt.datetime.fromtimestamp(e["when"]).astimezone()}
        self.w.show_result(e["route"], e["target"], e.get("argv"))

    def clear_history(self):
        answer = QMessageBox.question(self.w, "Clear history",
                                      f"Delete all {len(self.history)} saved traces?")
        if answer == QMessageBox.Yes:
            self._clear_history()

    # --------------------------------------------------------------- Atlas ---
    def atlas_trace(self):
        s = self.settings
        if not (s.atlas_enabled and s.atlas_key):
            self.open_settings(tab=3)
            return
        try:
            target = validate_target(self.w.target.text())
        except InvalidTarget as exc:
            self.w.summary.setText(f"<span style='color:#c0392b'>{exc}.</span>")
            return
        if not s.atlas_acknowledged:
            dialog = dialogs.AtlasWarningDialog(self.w, target=target)
            if not dialog.exec():
                return
            s.atlas_acknowledged = True
            config.save_settings(s)
        origin = self.origin

        def job(on_line, on_progress, cancel):
            async def go():
                client = atlas.Atlas(s.atlas_key, user_agent=service.user_agent())
                on_line("Finding a RIPE Atlas probe on your network…")
                me = await whereami.locate_me(user_agent=service.user_agent())
                asn = await whereami.asn_of(me["ip"], user_agent=service.user_agent())
                probe = await client.select_probe(asn, me.get("cc"), origin[:2] if origin else None)
                on_line(f"Probe #{probe['id']} (AS{probe.get('asn')}, {probe.get('country') or '?'})"
                        + (f", {probe['distance_km']:.0f} km from your origin"
                           if probe.get("distance_km") is not None else ""))
                measurement = await client.create(target, int(probe["id"]))
                on_line(f"Measurement {measurement} scheduled: "
                        f"https://atlas.ripe.net/measurements/{measurement}/")
                text = await client.wait(measurement, on_wait=lambda t: on_progress(
                    "trace", "started", f"waiting {t:.0f}s"))
                for line in text.splitlines():
                    on_line(line)
                on_progress("trace", "done")
                probe_origin = None
                label = f"RIPE Atlas probe #{probe['id']}"
                if probe.get("lat") is not None:
                    probe_origin = (round(probe["lat"], 2), round(probe["lon"], 2))
                route = await analyse(text, probe_origin, sources=service.sources_for(s),
                                      progress=lambda a, b, c: on_progress(a, b, c))
                if probe_origin:
                    route.origin["label"] = f"{label} near {route.origin['label']}"
                return {"route": route, "text": text,
                        "argv": ["RIPE Atlas", f"probe {probe['id']}", f"msm {measurement}", target],
                        "origin_how": "atlas"}
            return asyncio.run(go())

        self.w.show_tracing(target, ["RIPE Atlas", "traceroute", target], [], "scheduling")
        self.w.map.show_card(f"Tracing {target} from RIPE Atlas",
                             "The measurement runs on a probe near you and usually takes "
                             "30 to 90 seconds.")
        self._run(job, target=target, source=ATLAS)

    # ---------------------------------------------------------------- help ---
    def check_update(self):
        def job(on_line, on_progress, cancel):
            return asyncio.run(service.latest_release())

        task = Task(job, self)
        task.succeeded.connect(self._update_result)
        task.failed.connect(lambda m: self.error("Check for updates", f"GitHub did not answer: {m}"))
        self._update_task = task
        task.start()

    def _update_result(self, tag):
        current = f"v{__version__}"
        if not tag:
            text = "No release has been published yet."
        elif _norm(tag) == _norm(current):
            text = f"You have the latest release, {tag}."
        else:
            text = f"The latest release is {tag}; you have {current}.\n\n{REPO_URL}/releases"
        QMessageBox.information(self.w, "Check for updates", text)

    def about(self):
        QMessageBox.about(self.w, f"About {DISPLAY_NAME}", (
            f"<b>{DISPLAY_NAME}</b> {__version__}<br><br>"
            "Hostname-first, physics-checked traceroute maps. The trace runs on this machine.<br><br>"
            f"<a href='{REPO_URL}'>{REPO_URL}</a><br>GNU Affero General Public License v3.0<br><br>"
            "Hostname rules: CAIDA Hoiho. IP geolocation: RIPEstat (RIPE NCC). Cities: GeoNames, "
            "CC BY 4.0. Map: Natural Earth. Carrier sites: Arelion's looking glass. Built with Qt."))

    def save_window(self):
        self.settings.window_geometry = bytes(self.w.saveGeometry().toBase64()).decode()
        try:
            config.save_settings(self.settings)
        except OSError:
            pass
        if self.busy():
            self.task.stop()
            self.task.wait(3000)


# ------------------------------------------------------------------ helpers ---

def _norm(tag: str) -> str:
    return tag.lstrip("v").replace("-beta.", "b").replace("-", "")


def _html(text: str) -> str:
    import html
    return html.escape(text)


def _no_tool_html() -> str:
    return (f"Install one, then restart {DISPLAY_NAME}:<br><br>" + _html(install_hint()) +
            "<br><br>You can still analyse traces run elsewhere: <b>File › Paste Trace</b>.")


def write_export(fmt: str, path: str, current: dict, *, dark_png: bool = False,
                 include_trace: bool = True) -> None:
    """Write one export of *current* to *path*. Used by the window and the CLI."""
    route, target = current["route"], current["target"]
    label = service.tool_label(current.get("argv"))
    when = current.get("when") or _dt.datetime.now().astimezone()
    if fmt == "json":
        text = service.export_json(route, target=target, trace_text=current.get("trace_text", ""),
                                   argv=current.get("argv"), source=current.get("source", LOCAL),
                                   origin_how=current.get("origin_how"))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    elif fmt == "png":
        from routemap.gui import geometry
        image = mapview.render_png(
            route, dark=dark_png, title=f"{target} from {_city(route)}", destination=target,
            provenance=f"{DISPLAY_NAME} {__version__} \u00b7 {report.stamp(when)} \u00b7 "
                       f"{label or current.get('source', '')} · {geometry.ATTRIBUTION} · "
                       "GeoNames CC BY 4.0")
        if not image.save(path, "PNG"):
            raise OSError(f"could not write {path}")
    elif fmt == "pdf":
        report.write_pdf(path, route, target=target, trace_text=current.get("trace_text", ""),
                         tool_label=label, origin_how=current.get("origin_how"),
                         source=current.get("source", LOCAL), when=when, include_trace=include_trace)
    else:
        raise ValueError(f"unknown export format {fmt!r}")


def _city(route: dict) -> str:
    label = (route.get("origin") or {}).get("label") or "unknown origin"
    return label.split(",")[0]


def headless_platform() -> None:
    """Pick a Qt platform for work with no visible window (CLI exports, smoke test).

    Only Linux without a display needs "offscreen". Elsewhere the native platform
    renders fine with no window shown, and must be used: on Windows the offscreen
    platform has no font database, so text in a PNG or PDF comes out empty.
    """
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY")
                                                  or os.environ.get("WAYLAND_DISPLAY")):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"


def make_app(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance() or QApplication(argv or [sys.argv[0]])
    app.setApplicationName(DISPLAY_NAME)
    app.setApplicationDisplayName(DISPLAY_NAME)
    app.setOrganizationName(NAME)
    app.setApplicationVersion(__version__)
    icon_path = os.path.join(os.path.dirname(__file__), "data", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    return app


def run_gui(target: str | None = None, origin_override: tuple | None = None) -> int:
    app = make_app()
    service.startup()
    settings = config.load_settings()
    window = MainWindow()
    controller = Controller(window, settings)
    if origin_override:
        controller.origin, controller.origin_how = origin_override, "coords"
    controller.start()
    window.show()
    if target:
        window.target.setText(target)
        QTimer.singleShot(200, controller.trace)
    return app.exec()
