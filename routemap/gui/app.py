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
import pathlib
import sys

from PySide6.QtCore import QByteArray, QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from routemap import bugreport, config, dbip, imported, insight, service, updater
from routemap.__about__ import (DISPLAY_NAME, NAME, REPO_URL, engine_line, version_line,
                                CONTACT_EMAIL, WINDOWS_SIGNED, SITE_LINKED, SITE_URL,
                                VERSION)
from routemap_engine import (InvalidTarget, Route, SqliteCache, TraceParseError, analyse, atlas,
                             available_tools, install_hint, validate_target, whereami)
from routemap_engine.runner import TraceToolMissing, pick_tool
from routemap.gui import dialogs, mapview, report
from routemap_engine import diff as route_diff
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
        self.insight_task: Task | None = None
        self.detail_task: Task | None = None
        self.generation = 0               # bumps per shown result; stale background answers are dropped
        self.compare_next: dict | None = None   # the route to compare the next result with
        self.comparison: dict | None = None     # {"old", "diff", "label"} while one is shown
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
        w.act_bug.triggered.connect(self.bug_report)
        w.act_tour.triggered.connect(self.show_tour)
        w.act_notices.triggered.connect(lambda: dialogs.NoticesDialog(w).exec())
        w.act_about.triggered.connect(self.about)
        # Only when chosen from the menu; the app never asks on its own.
        w.act_support.triggered.connect(lambda: dialogs.SupportDialog(w).exec())
        w.history.opened.connect(self.open_history)
        w.history.cleared.connect(self.clear_history)
        w.map.originPicked.connect(self._picked)
        w.closing = self.save_window
        w.act_again.triggered.connect(self.trace_again)
        w.act_compare_file.triggered.connect(self.compare_with_file)
        w.act_compare_atlas.triggered.connect(self.compare_with_atlas)
        w.act_end_compare.triggered.connect(self.end_comparison)
        w.table.hopsSelected.connect(self._hops_selected)
        w.details.openFalconEye.connect(self.open_falconeye)
        w.table.setContextMenuPolicy(Qt.CustomContextMenu)
        w.table.customContextMenuRequested.connect(self._table_menu)
        w.map.projectionChanged.connect(self._projection_changed)
        w.refresh_panels = self.refresh_panels
        w.themeChosen.connect(self.set_theme)

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
        self.w.map.set_thresholds(self.settings.rtt_quiet_ms, self.settings.rtt_hot_ms)
        self.w.map.set_projection(self.settings.projection)
        self.w.act_globe.setChecked(self.settings.projection == "globe")
        self.w.sync_theme_menu(self.settings.theme)
        self._refresh_compare_actions()
        self.show_idle()
        if self.origin is None:
            self.lookup_origin()
        QTimer.singleShot(700, self.first_run)

    def first_run(self):
        """The one-time offers, in order: the city database, then the tour."""
        self.offer_city_database()
        if not self.settings.tour_seen:
            self.show_tour()

    def show_tour(self):
        from routemap.gui.tour import Tour
        if getattr(self, "_tour", None) is not None:
            return
        self._tour = Tour(self.w)

        def done():
            self._tour = None
            if not self.settings.tour_seen:
                self.settings.tour_seen = True
                config.save_settings(self.settings)

        self._tour.finished.connect(done)

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
        from routemap import policy
        if not (policy.RIPESTAT_ALLOWED and self.settings.online_lookups):
            self._refresh_origin_status()
            return

        def job(on_line, on_progress, cancel, **_):
            return asyncio.run(whereami.locate_me(user_agent=service.user_agent(),
                                                  sourceapp=service.SOURCEAPP))

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

        def job(on_line, on_progress, cancel, on_hop, **_):
            return progressive_trace(target, settings, origin, on_line=on_line,
                                     on_progress=on_progress, on_hop=on_hop, cancel=cancel)

        from routemap_engine.runner import build_argv
        argv = build_argv(tool, tool, target, settings.flags_for(tool))
        self.w.show_tracing(target, argv)
        if origin:
            self.w.map.set_origin(*origin)
        if self.compare_next is not None:
            # Trace again: the earlier run stays on the map, faint, while this one grows.
            self.comparison = None
            self.w.map.set_comparison(self.compare_next["route"], None)
        else:
            self._end_comparison_quietly()
        self._run(job, target=target, source=LOCAL)

    def _run(self, job, *, target: str, source: str):
        task = Task(job, self)
        task.line.connect(self._line)
        task.progress.connect(lambda s, st, d: self.w.sources.set_state(s, st, d or None))
        task.hop.connect(lambda route: self._hop(route, target))
        task.succeeded.connect(lambda r: self._done(r, target, source))
        task.failed.connect(self._failed)
        self.task = task
        self.w.set_running(True)
        task.start()

    def _line(self, line: str):
        self.w.live.append(line)
        stripped = line.strip()
        number = stripped.split()[0].rstrip(".|-") if stripped else ""
        if number.isdigit():
            self._hop_note = f"hop {number}"
            self.w.sources.set_state("trace", "started", self._hop_note)

    def _hop(self, route: dict, target: str):
        """One more hop placed while the tool is still running: draw it now."""
        if not self.busy():
            return
        self.w.update_live(route, target, getattr(self, "_hop_note", ""))

    def _done(self, result: dict, target: str, source: str):
        route: Route = result["route"]
        body = route.to_dict()
        self.current = {"route": body, "target": target, "trace_text": result["text"],
                        "argv": result.get("argv"), "source": source,
                        "origin_how": result.get("origin_how") or (
                            self.origin_how if body["origin"]["source"] == "supplied" else "first-hop"),
                        "when": _dt.datetime.now().astimezone()}
        self.w.show_result(body, target, result.get("argv"), trace_text=result["text"],
                           keep_view=source == LOCAL)
        if result.get("stopped"):
            self.w.statusBar().showMessage(f"Stopped; the {len(body['hops'])} hops traced so "
                                           "far are shown.", 10000)
        if result.get("timed_out"):
            self.w.statusBar().showMessage("The trace hit its time limit; the hops it reached "
                                           "are shown.", 10000)
        self._after_result()
        entry = config.history_entry(body, target=target, trace_text=result["text"],
                                     argv=result.get("argv"), source=source)
        entry["origin_how"] = self.current["origin_how"]
        config.add_history(entry, self.settings)
        self.refresh_history()

    def _failed(self, message: str):
        self.compare_next = None
        self.w.set_running(False)
        self.w.set_state("")
        self.w.sources.hide()
        if self.current:
            c = self.current
            self.w.show_result(c["route"], c["target"], c.get("argv"), trace_text=c.get("trace_text"))
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
        self.open_path(path)

    def open_path(self, path: str):
        """Open a trace or a route export. An export is rebuilt from the route
        format before anything in it is shown (imported.export), and its saved
        insight is computed again rather than trusted."""
        try:
            text = imported.read_file(path)
        except imported.ImportRejected as exc:
            self.error("Could not open the file", str(exc))
            return
        if path.lower().endswith(".json"):
            try:
                doc = imported.export(imported.parse_json(text))
                Route.from_dict(doc["route"])
            except (ValueError, KeyError, TypeError) as exc:
                self.error("Not a route export", f"That JSON file is not a routemap export. {exc}")
                return
            self.current = {"route": doc["route"], "target": doc["target"] or os.path.basename(path),
                            "trace_text": doc["trace_text"], "argv": doc["argv"], "source": doc["source"],
                            "origin_how": doc["origin_how"], "when": _dt.datetime.now().astimezone()}
            self.w.show_result(doc["route"], self.current["target"], self.current["argv"],
                               trace_text=self.current["trace_text"])
            self._after_result()
            return
        self.analyse_text(text, os.path.basename(path), FILE)

    def analyse_text(self, text: str, label: str, source: str):
        if self.busy():
            return
        settings, origin = self.settings, self.origin

        def job(on_line, on_progress, cancel, **_):
            route = asyncio.run(analyse(text, origin[:2] if origin else None,
                                        sources=service.sources_for(settings),
                                        progress=lambda s, st, d: on_progress(s, st, d)))
            return {"route": route, "text": text, "argv": None}

        try:
            from routemap_engine import parse_trace
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
        self.w.set_state(f"Analysing <b>{_html(target)}</b>…")
        self._run(job, target=target, source=source)

    # -------------------------------------------------------------- export ---
    def export(self):
        if not self.current:
            self.error("Nothing to export", "Trace a route, paste a trace or open one first.")
            return
        dialog = dialogs.ExportDialog(self.w, selected="pdf")
        from routemap.gui import theme as _theme
        dialog.png_dark.setChecked(_theme.is_dark())
        if not dialog.exec():
            return
        fmt = dialog.selected()
        c = self.current
        stem = service.export_stem(c["target"], c["when"])
        filters = {"png": "PNG image (*.png)", "pdf": "PDF report (*.pdf)", "json": "JSON (*.json)"}
        path, _ = QFileDialog.getSaveFileName(self.w, "Export", os.path.join(
            os.path.expanduser("~"), f"{stem}.{fmt}"), filters[fmt])
        if not path:
            return
        if not path.lower().endswith("." + fmt):
            path += "." + fmt
        try:
            write_export(fmt, path, c, dark_png=dialog.png_dark.isChecked(),
                         include_trace=dialog.appendix.isChecked(), settings=self.settings)
        except Exception as exc:  # noqa: BLE001
            self.error("Export failed", str(exc))
            return
        self.w.statusBar().showMessage(f"Exported {os.path.basename(path)}", 6000)

    # ------------------------------------------------------------ settings ---
    def open_settings(self, tab: int = 0):
        cache_count = 0
        # Every answer cache: Hoiho hostnames, IP database addresses, RIPE details.
        for path in (config.cache_path(), config.ip_cache_path(), config.ripe_cache_path()):
            try:
                if os.path.exists(path):
                    cache_count += len(SqliteCache(path))
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
        dialog.updateDataRequested.connect(lambda: self.update_databases(dialog))
        dialog.importDataRequested.connect(lambda: self.import_city_database(dialog))
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
        self._refresh_compare_actions()
        self.refresh_history()
        self.w.map.set_thresholds(self.settings.rtt_quiet_ms, self.settings.rtt_hot_ms)
        from routemap.gui import theme as _theme
        if self.settings.theme != _theme.choice():
            self.set_theme(self.settings.theme)
        if self.settings.projection != self.w.map.projection:
            self.w.map.set_projection(self.settings.projection)
            self.w.act_globe.setChecked(self.settings.projection == "globe")
        if self.current is not None:
            # Sensitive countries and the online switch change what the panel says.
            self.current["insight"] = None
            self._after_result(keep_comparison=True)
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
            for extra in (config.ip_cache_path(), config.ripe_cache_path()):
                if os.path.exists(extra):
                    removed += SqliteCache(extra).clear()
        except Exception as exc:  # noqa: BLE001
            self.error("Clear cache", str(exc))
            return
        dialog.clear_cache.setText(f"Cleared ({removed} answers)")
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
        self.w.show_result(e["route"], e["target"], e.get("argv"), trace_text=e.get("trace_text", ""))
        self._after_result()

    def clear_history(self):
        answer = QMessageBox.question(self.w, "Clear history",
                                      f"Delete all {len(self.history)} saved traces?")
        if answer == QMessageBox.Yes:
            self._clear_history()

    # --------------------------------------------------------------- Atlas ---
    def atlas_trace(self):
        s = self.settings
        if not (s.atlas_enabled and s.atlas_key):
            self.open_settings(tab=dialogs.SettingsDialog.ATLAS_TAB)
            return
        try:
            target = validate_target(self.w.target.text())
        except InvalidTarget as exc:
            self.w.summary.setText(f"<span style='color:#c0392b'>{exc}.</span>")
            return
        dialog = dialogs.AtlasTraceDialog(self.w, target=target, acknowledged=s.atlas_acknowledged)

        def read_balance(on_line, on_progress, cancel, **_):
            # Only the key goes to RIPE here, to its own credits endpoint.
            return asyncio.run(atlas.Atlas(s.atlas_key, user_agent=service.user_agent()).balance())

        balance_task = Task(read_balance, self)
        balance_task.succeeded.connect(
            lambda b: dialog.set_credits(service.atlas_credit_view(b, atlas.TRACEROUTE_CREDITS)))
        balance_task.failed.connect(lambda _m: dialog.set_credits(service.atlas_credit_view(
            atlas.Balance("unavailable"), atlas.TRACEROUTE_CREDITS)))
        self._balance_task = balance_task
        balance_task.start()
        answer = dialog.exec()
        if answer == dialogs.AtlasTraceDialog.SETTINGS:
            self.open_settings(tab=dialogs.SettingsDialog.ATLAS_TAB)
            return
        if not answer:
            return
        if not s.atlas_acknowledged:
            s.atlas_acknowledged = True
            config.save_settings(s)
        origin = self.origin

        def job(on_line, on_progress, cancel, **_):
            async def go():
                client = atlas.Atlas(s.atlas_key, user_agent=service.user_agent(),
                                     description=f"{DISPLAY_NAME} traceroute")
                on_line("Finding a RIPE Atlas probe on your network…")
                from routemap import policy
                from routemap_engine import cities as _cities
                asn, cc = None, None
                if policy.RIPESTAT_ALLOWED and s.online_lookups:
                    me = await whereami.locate_me(user_agent=service.user_agent(),
                                                  sourceapp=service.SOURCEAPP)
                    asn = await whereami.asn_of(me["ip"], user_agent=service.user_agent(),
                                                sourceapp=service.SOURCEAPP)
                    cc = me.get("cc")
                elif origin:
                    cc = ((_cities.nearest(origin[0], origin[1]) or {}).get("cc"))
                probe = await client.select_probe(asn, cc, origin[:2] if origin else None)
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
        self.w.set_state(f"Tracing <b>{target}</b> from a RIPE Atlas probe (usually 30 to 90 s)")
        self._run(job, target=target, source=ATLAS)

    # ------------------------------------------------------------- insight ---
    def _after_result(self, saved: dict | None = None, keep_comparison: bool = False):
        """A route is on screen: say what it is beyond places. Offline now,
        online in the background. Also settles any pending comparison."""
        c = self.current
        if c is None:
            return
        self.generation += 1
        generation = self.generation
        settings = self.settings
        if saved and isinstance(saved, dict):
            c["insight"] = saved
        else:
            c["insight"] = insight.offline(c["route"], settings)
        # The offline step added DB-IP ASNs to the hops: redraw, so the map's
        # credit line names DB-IP as soon as its data is on screen.
        self.w.map.set_route(c["route"], c["target"], keep_view=True)
        if self.compare_next is not None:
            old, self.compare_next = self.compare_next, None
            self._start_comparison(old["route"], old.get("label") or "the earlier run")
        elif not keep_comparison:
            self._end_comparison_quietly()
        self.refresh_panels()
        if saved or not insight.online_allowed(settings):
            if not saved:
                c["insight"]["online"] = {"status": insight.OFF}
                self.refresh_panels()
            return
        route, ins = c["route"], c["insight"]

        def job(on_line, on_progress, cancel, **_):
            return asyncio.run(insight.online(route, ins, settings, user_agent=service.user_agent(),
                                              sourceapp=service.SOURCEAPP))

        task = Task(job, self)
        task.succeeded.connect(lambda _r: self._insight_done(generation))
        task.failed.connect(lambda _m: self._insight_done(generation))
        self.insight_task = task
        task.start()

    def _insight_done(self, generation: int):
        if generation != self.generation or self.current is None:
            return
        self.w.map.set_route(self.current["route"], self.current["target"], keep_view=True)
        self.refresh_panels()

    def _origin_cc(self) -> str | None:
        from routemap_engine import cities as _cities
        origin = (self.current or {}).get("route", {}).get("origin") or {}
        if origin.get("lat") is None:
            return None
        return (_cities.nearest(origin["lat"], origin["lon"], max_km=400) or {}).get("cc")

    def refresh_panels(self):
        c = self.current
        if c is None:
            return
        ins = c.get("insight")
        details = ((ins or {}).get("online") or {}).get("hops") or {}
        marks = (self.comparison or {}).get("diff", {}).get("new_marks")
        self.w.table.set_hops(c["route"].get("hops") or [], details, marks)
        cmp = self.comparison
        self.w.insight.show_summary(c["route"], ins, origin_cc=self._origin_cc(),
                                    diff=cmp["diff"] if cmp else None,
                                    diff_label=cmp["label"] if cmp else "")
        self._hops_selected(self.w.table.selected_hops())

    def _hops_selected(self, hops: list):
        c = self.current
        if c is None or len(hops) != 1:
            self.w.details.hide()
            return
        hop = next((h for h in c["route"].get("hops") or [] if h["hop"] == hops[0]), None)
        if hop is None:
            self.w.details.hide()
            return
        cache = c.setdefault("hop_extra", {})
        extra = cache.get(hop["hop"])
        self.w.details.show_hop(hop, c.get("insight"), extra)
        if extra is not None:
            return
        settings, generation = self.settings, self.generation

        def job(on_line, on_progress, cancel, **_):
            return asyncio.run(insight.hop_details(hop, settings, user_agent=service.user_agent(),
                                                   sourceapp=service.SOURCEAPP))

        def done(result):
            if generation != self.generation or self.current is not c:
                return
            cache[hop["hop"]] = result
            if self.w.table.selected_hops() == [hop["hop"]]:
                self.w.details.show_hop(hop, c.get("insight"), result)

        task = Task(job, self)
        task.succeeded.connect(done)
        task.failed.connect(lambda _m: done({"rir": insight.UNAVAILABLE, "abuse": insight.UNAVAILABLE,
                                             "status": insight.UNAVAILABLE}))
        self.detail_task = task
        task.start()

    def open_falconeye(self, address: str):
        """FalconEye's IP Reputation tab, with the address on the clipboard to
        paste. The address is not put in the URL: nothing is sent to FalconEye
        until the user runs the lookup there."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if not address:
            return
        QGuiApplication.clipboard().setText(address)
        QDesktopServices.openUrl(QUrl(f"{self.settings.falconeye_url}/#ip"))
        self.w.statusBar().showMessage(f"Opened FalconEye; {address} is on the clipboard to paste "
                                       "into IP Reputation.", 8000)

    def _table_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        hops = self.w.table.selected_hops()
        if self.current is None or len(hops) != 1:
            return
        hop = next((h for h in self.current["route"]["hops"] if h["hop"] == hops[0]), None)
        address = next((a for a in (hop or {}).get("addresses") or []
                        if mapview_public(a)), None)
        menu = QMenu(self.w.table)
        copy = menu.addAction("Copy Address")
        copy.setEnabled(bool((hop or {}).get("addresses")))
        abuse = menu.addAction("Copy Abuse Contact")
        abuse.setEnabled(bool(self.w.details.abuse))
        menu.addSeparator()
        falcon = menu.addAction("Open in FalconEye")
        falcon.setEnabled(bool(address))
        chosen = menu.exec(self.w.table.viewport().mapToGlobal(pos))
        if chosen is copy:
            QGuiApplication.clipboard().setText(", ".join(hop.get("addresses") or []))
        elif chosen is abuse:
            QGuiApplication.clipboard().setText(", ".join(self.w.details.abuse))
        elif chosen is falcon:
            self.open_falconeye(address)

    def _projection_changed(self, projection: str):
        self.settings.projection = projection
        try:
            config.save_settings(self.settings)
        except OSError:
            pass

    def set_theme(self, choice: str):
        """System, Light or Dark: the window, the map and the exports. Remembered."""
        from routemap.gui import theme
        self.settings.theme = choice
        try:
            config.save_settings(self.settings)
        except OSError:
            pass
        theme.apply(QApplication.instance(), choice)
        self.w.sync_theme_menu(choice)
        self.w._theme_changed()

    # ----------------------------------------------------------- compare ---
    def _refresh_compare_actions(self):
        s = self.settings
        self.w.act_compare_atlas.setEnabled(bool(s.atlas_enabled and s.atlas_key and s.online_lookups))
        self.w.act_compare_atlas.setToolTip("" if self.w.act_compare_atlas.isEnabled() else
                                            "Needs RIPE Atlas with your key, and Online lookups on")

    def _label_for(self, current: dict) -> str:
        when = current.get("when")
        return when.strftime("%-d %b %H:%M" if sys.platform != "win32" else "%d %b %H:%M") \
            if when else "the earlier run"

    def trace_again(self):
        """Run the current target again, then show the two runs compared."""
        c = self.current
        if c is None or self.busy():
            self.error("Trace again", "Trace a route first; the next run is compared with it.")
            return
        self.compare_next = {"route": c["route"], "label": self._label_for(c)}
        self.w.target.setText(c["target"])
        self.trace()
        if not self.busy():
            self.compare_next = None

    def compare_with_file(self):
        """Compare the route on screen with an earlier JSON export."""
        if self.current is None:
            self.error("Compare", "Trace or open a route first, then choose the export to compare with.")
            return
        path, _ = QFileDialog.getOpenFileName(self.w, "Compare with an export", os.path.expanduser("~"),
                                              "Route exports (*.json)")
        if not path:
            return
        try:
            doc = imported.export(imported.parse_json(imported.read_file(path)))
            old = doc["route"]
            Route.from_dict(old)
        except (ValueError, KeyError, TypeError) as exc:
            self.error("Not a route export", f"That JSON file is not a routemap export. {exc}")
            return
        label = (doc["exported_at"] or os.path.basename(path))[:16].replace("T", " ")
        self._start_comparison(old, label)
        self.refresh_panels()

    def compare_with_atlas(self):
        """Compare with the newest of the user's own earlier Atlas traceroutes to
        this target: no credits spent, the key and the target go to RIPE Atlas."""
        c, s = self.current, self.settings
        if c is None:
            self.error("Compare", "Trace or open a route first.")
            return
        target = c["target"]
        origin = self.origin

        def job(on_line, on_progress, cancel, **_):
            async def go():
                client = atlas.Atlas(s.atlas_key, user_agent=service.user_agent())
                found = await client.history(target, limit=3)
                if not found:
                    raise RuntimeError(f"No earlier Atlas traceroutes of yours to {target} were found.")
                newest = found[0]
                route = await analyse(newest["text"], origin[:2] if origin else None,
                                      sources=service.sources_for(s))
                return {"route": route.to_dict(), "label": f"Atlas msm {newest['msm']}"}
            return asyncio.run(go())

        task = Task(job, self)
        task.succeeded.connect(lambda r: (self._start_comparison(r["route"], r["label"]), self.refresh_panels()))
        task.failed.connect(lambda m: self.error("Compare with Atlas", m))
        self._atlas_history_task = task
        self.w.statusBar().showMessage("Asking RIPE Atlas for your earlier measurements…", 5000)
        task.start()

    def _start_comparison(self, old: dict, label: str):
        c = self.current
        if c is None:
            return
        result = route_diff.diff_routes(old, c["route"])
        self.comparison = {"old": old, "diff": result, "label": label}
        self.w.map.set_comparison(old, result["new_marks"])
        self.w.act_end_compare.setEnabled(True)
        c["comparison"] = {"label": label, "summary": result["summary"], "changes": result["changes"],
                           "old_route": old, "new_marks": result["new_marks"],
                           "old_marks": result["old_marks"]}

    def _end_comparison_quietly(self):
        if self.comparison is not None:
            self.comparison = None
            self.w.map.set_comparison(None, None)
        self.w.act_end_compare.setEnabled(False)
        if self.current is not None:
            self.current.pop("comparison", None)

    def end_comparison(self):
        self._end_comparison_quietly()
        self.refresh_panels()

    # ----------------------------------------------------------- databases ---
    def offer_city_database(self):
        """First run: offer DB-IP Lite City, once. Never downloads unasked."""
        s = self.settings
        if dbip.city_database() is not None or s.city_db_declined or not s.online_lookups:
            return
        choice = dialogs.CityDatabaseDialog(self.w).exec()
        if choice == dialogs.CityDatabaseDialog.DOWNLOAD:
            self.update_databases()
        elif choice == dialogs.CityDatabaseDialog.IMPORT:
            self.import_city_database()
        else:
            s.city_db_declined = True
            config.save_settings(s)

    def update_databases(self, settings_dialog=None):
        """Download this month's DB-IP Lite City and ASN, with a progress bar."""
        progress = dialogs.DownloadDialog(self.w)

        def job(on_line, on_progress, cancel, **_):
            out = []
            for kind in ("city", "asn"):
                on_line(kind)
                out.append(dbip.download(kind, user_agent=service.user_agent(),
                                         progress=lambda done, total: on_progress(kind, str(done), str(total or 0)),
                                         cancelled=cancel.is_set))
            return out

        task = Task(job, self)
        task.line.connect(progress.set_kind)
        task.progress.connect(lambda kind, done, total: progress.set_progress(int(done), int(total)))
        task.succeeded.connect(lambda dbs: (progress.accept(), self._databases_installed(dbs, settings_dialog)))
        task.failed.connect(lambda m: (progress.reject(), self.error("DB-IP download", m)))
        progress.rejected.connect(task.stop)
        self._db_task = task
        task.start()
        progress.exec()

    def import_city_database(self, settings_dialog=None):
        path, _ = QFileDialog.getOpenFileName(self.w, "Import DB-IP Lite City", os.path.expanduser("~"),
                                              "DB-IP Lite City (*.mmdb *.mmdb.gz);;All files (*)")
        if not path:
            return
        try:
            db = dbip.import_file(path, "city")
        except dbip.DatabaseError as exc:
            self.error("Import database", str(exc))
            return
        self._databases_installed([db], settings_dialog)

    def _databases_installed(self, dbs: list, settings_dialog=None):
        insight._ASN = None
        months = ", ".join(d.label for d in dbs)
        self.w.statusBar().showMessage(f"Installed {months}.", 8000)
        if settings_dialog is not None:
            settings_dialog.refresh_databases()

    # ---------------------------------------------------------------- help ---
    def check_update(self):
        def job(on_line, on_progress, cancel, **_):
            return asyncio.run(service.latest_release())

        task = Task(job, self)
        task.succeeded.connect(self._update_result)
        task.failed.connect(lambda m: self.error("Check for updates", f"GitHub did not answer: {m}"))
        self._update_task = task
        task.start()

    def _update_result(self, latest):
        current = f"v{VERSION}"
        box = QMessageBox(self.w)
        box.setTextFormat(Qt.PlainText)
        box.setWindowTitle("Check for updates")
        box.setIcon(QMessageBox.Icon.Information)
        if not latest:
            box.setText("No release has been published yet.")
            box.exec()
            return
        tag, mine = latest["tag"], service.release_order(current)
        if service.release_order(tag) == mine:
            box.setText(f"You have the latest release, {tag}.")
            box.exec()
            return
        if mine and service.release_order(tag) < mine:
            box.setText(f"You have {current}, newer than the latest release, {tag}.")
            box.exec()
            return
        offer = service.installer_for(latest["assets"])
        if offer and not service.release_url(offer[1]):
            offer = None
        if offer and updater.available(latest):
            self._update_in_app(latest, offer[0], current)
            return
        digest = (latest.get("digests") or {}).get(offer[0]) if offer else None
        box.setText(f"{DISPLAY_NAME} {tag} is out; you have {current}.")
        box.setInformativeText(
            (f"For this computer: {offer[0]}. Your browser downloads it; install it over this "
             "version, and your settings and history stay." if offer else
             "The release has no download for this platform; the release page lists every file.")
            + (f"\n\nIts SHA-256 is\n{digest}\nCheck the downloaded file with\n"
               f"{service.verify_command(offer[0])}\nand compare, or check it against the signed "
               "SHA256SUMS on the release page." if digest else ""))
        get = box.addButton("Download" if offer else "Open the release page", QMessageBox.ButtonRole.AcceptRole)
        notes = box.addButton("Release notes", QMessageBox.ButtonRole.HelpRole) if offer else None
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        page = service.release_url(latest.get("page")) or f"{REPO_URL}/releases"
        if box.clickedButton() is get:
            QDesktopServices.openUrl(QUrl(offer[1] if offer else page))
        elif notes is not None and box.clickedButton() is notes:
            QDesktopServices.openUrl(QUrl(page))

    def bug_report(self):
        current = getattr(self, "current", None) or None
        label = (current or {}).get("target") or ""
        dialog = dialogs.BugReportDialog(
            self.w, build=lambda include: bugreport.contents(self.settings, current, include),
            has_trace=bool(current and current.get("route")), trace_label=label)
        if not dialog.exec():
            return
        stem = bugreport.suggested_name(_dt.datetime.now())
        path, _ = QFileDialog.getSaveFileName(self.w, "Save the bug report", stem, "Zip (*.zip)")
        if not path:
            return
        try:
            bugreport.write_zip(path, dialog.contents)
        except OSError as exc:
            self.error("Create Bug Report", f"The zip could not be saved: {exc.strerror or exc}")

    def _update_in_app(self, latest: dict, name: str, current: str):
        """Download, check and hand over the release file (routemap/updater.py)."""
        dialog = dialogs.UpdateDialog(self.w, tag=latest["tag"], current=current, name=name)
        state = {"task": None, "path": None, "workdir": None}

        def job(on_line, on_progress, cancel, **_):
            work = updater.private_dir()
            state["workdir"] = work
            try:
                path = updater.download_and_verify(
                    latest, name, work, on_step=lambda s, st: on_progress(s, st, ""),
                    on_bytes=lambda w, tot: on_progress("bytes", str(w), str(tot or "")), cancel=cancel)
            except updater.UpdateFailed as exc:
                return {"failed": exc.step, "message": exc.message}
            return {"path": str(path)}

        def progress(source, st, detail):
            if source == "bytes":
                dialog.bytes_done(int(st), int(detail) if detail else None)
            else:
                dialog.step("hash" if source == updater.STEP_LISTED else source, st)

        def finished(result):
            if result.get("failed"):
                dialog.failed(result["failed"], result["message"])
                return
            state["path"] = pathlib.Path(result["path"])
            plan = updater.plan(state["path"], sys.platform, os.environ.get("APPIMAGE"))
            state["plan"] = plan
            action = {"installer": "Install and quit", "replace": "Restart with the update"}.get(
                plan["kind"], "Open")
            dialog.verified(plan["text"], action)

        def start():
            task = Task(job, self)
            task.progress.connect(progress)
            task.succeeded.connect(finished)
            task.failed.connect(lambda m: dialog.failed(updater.STEP_DOWNLOAD, m))
            state["task"] = task
            dialog.checking()
            task.start()

        dialog.go.clicked.connect(start)
        answer = dialog.exec()
        task = state["task"]
        if task is not None and task.isRunning():
            task.stop()
            task.wait(5000)
        page = service.release_url(latest.get("page")) or f"{REPO_URL}/releases"
        if answer == dialogs.UpdateDialog.NOTES:
            QDesktopServices.openUrl(QUrl(page))
        if answer != dialogs.UpdateDialog.HAND_OVER or state["path"] is None:
            if state["workdir"] is not None:
                updater.discard(state["workdir"])
            return
        self._hand_over(state["plan"], state["path"], state["workdir"])

    def _hand_over(self, plan: dict, path, workdir):
        import subprocess
        try:
            if plan["kind"] == "replace":
                updater.replace_appimage(path, plan["argv"][0])
                updater.discard(workdir)
                subprocess.Popen(plan["argv"], start_new_session=True)
                QApplication.quit()
            elif plan["kind"] == "installer":
                flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                subprocess.Popen(plan["argv"], creationflags=flags)
                QApplication.quit()
            elif plan["argv"]:
                # The system's own installer reads the file from the private folder;
                # the folder is the operating system's temporary space and is left to it.
                subprocess.Popen(plan["argv"], start_new_session=True)
        except (OSError, updater.UpdateFailed) as exc:
            updater.discard(workdir)
            self.error("Update", getattr(exc, "message", None) or str(exc))

    def about(self):
        QMessageBox.about(self.w, f"About {DISPLAY_NAME}", (
            f"<b>{DISPLAY_NAME}</b> {_html(version_line())}<br><br>"
            "Hostname-first, physics-checked traceroute maps. The trace runs on this machine.<br><br>"
            f"Free software under the GNU AGPL-3.0: <a href='{REPO_URL}'>{REPO_URL}</a>. "
            "Third-party components keep their own licences: Help \u203a Third-Party Notices."
            "<br>Geolocation engine: "
            f"<a href='https://github.com/osintph/routemap-engine'>routemap-engine</a>"
            f"{_html(engine_line().removeprefix('routemap-engine'))} (AGPL-3.0)<br><br>"
            "Hostname rules: CAIDA Hoiho. IP geolocation and route details: RIPEstat and RIPE Atlas "
            "(RIPE NCC); IP Geolocation by <a href='https://db-ip.com'>DB-IP</a> (CC BY 4.0). "
            "Cities: GeoNames, CC BY 4.0. Map: Natural Earth. Carrier sites: Arelion's looking "
            "glass. Built with Qt."
            + ("<br><br>" + (f"<a href='{SITE_URL}'>{SITE_URL}</a> \u00b7 " if SITE_LINKED else "")
               + f"<a href='mailto:{CONTACT_EMAIL}'>{CONTACT_EMAIL}</a> \u00b7 "
               + "Support this project: Help \u203a Support")
            + ("<br><br>Windows builds are code-signed by the maintainer (Certum)."
               if WINDOWS_SIGNED and sys.platform == "win32" else "")))

    def save_window(self):
        self.settings.window_geometry = bytes(self.w.saveGeometry().toBase64()).decode()
        try:
            config.save_settings(self.settings)
        except OSError:
            pass
        if self.busy():
            self.task.stop()
            self.task.wait(3000)


# --------------------------------------------------------- the live trace ---

def progressive_trace(target: str, settings: config.Settings, origin, *, on_line, on_progress,
                      on_hop, cancel) -> dict:
    """Run the tool and place each hop as its line arrives. Blocking; worker thread.

    Two threads cooperate: this one reads the tool's output (and must never wait
    on the network, or the output would stall), and a placer thread with its own
    event loop parses each line and places hops in order, one at a time, calling
    *on_hop* with the route so far after each. When the tool exits, the placer
    finishes what is queued and runs the final pass (ECMP and annotations).
    Stopping keeps whatever was traced.
    """
    import copy
    import threading

    from routemap_engine.progressive import ProgressiveTrace, _signature

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, name="routemap-placer", daemon=True)
    thread.start()
    trace = ProgressiveTrace(origin[:2] if origin else None, service.sources_for(settings),
                             progress=lambda s, st, d: on_progress(s, st, d))

    async def make_queue():
        return asyncio.Queue()

    queue = asyncio.run_coroutine_threadsafe(make_queue(), loop).result()

    async def placer():
        while True:
            number = await queue.get()
            try:
                if number is None:
                    return
                hop = trace.hops.get(number)
                if hop is not None and trace.placed_sig.get(number) != _signature(hop):
                    await trace.place(hop)
                    on_hop(copy.deepcopy(trace.snapshot()))
            except Exception as exc:  # noqa: BLE001 - one hop never stops the trace
                on_progress("trace", "failed", f"hop {number}: {exc}")
            finally:
                queue.task_done()

    asyncio.run_coroutine_threadsafe(placer(), loop)

    def handle(line: str):          # on the placer's loop
        for hop in trace.feed(line):
            queue.put_nowait(hop.hop)

    def line_seen(line: str):       # on this thread
        on_line(line)
        loop.call_soon_threadsafe(handle, line)

    async def final():
        await queue.join()
        await queue.put(None)
        return await trace.finish()

    try:
        result = service.run(target, settings, cancel=cancel, on_line=line_seen)
        if not result.text.strip():
            raise RuntimeError(f"{result.tool} printed nothing (exit code {result.returncode}).")
        if result.cancelled and not trace.hops:
            raise RuntimeError("Stopped before the first hop.")
        on_progress("trace", "done")
        route = asyncio.run_coroutine_threadsafe(final(), loop).result()
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
    return {"route": route, "text": result.text, "argv": result.argv,
            "timed_out": result.timed_out, "stopped": result.cancelled}


# ------------------------------------------------------------------ helpers ---

def mapview_public(address: str) -> bool:
    from routemap_engine.geo import classify_address
    return classify_address(address) == "public"



def _html(text: str) -> str:
    import html
    return html.escape(text)


def _no_tool_html() -> str:
    return (f"Install one, then restart {DISPLAY_NAME}:<br><br>" + _html(install_hint()) +
            "<br><br>You can still analyse traces run elsewhere: <b>File › Paste Trace</b>.")


def write_export(fmt: str, path: str, current: dict, *, dark_png: bool = False,
                 include_trace: bool = True, settings: config.Settings | None = None) -> None:
    """Write one export of *current* to *path*. Used by the window and the CLI."""
    route, target = current["route"], current["target"]
    settings = settings or config.Settings()
    ins, cmp = current.get("insight"), current.get("comparison")
    label = service.tool_label(current.get("argv"))
    when = current.get("when") or _dt.datetime.now().astimezone()
    if fmt == "json":
        text = service.export_json(route, target=target, trace_text=current.get("trace_text", ""),
                                   argv=current.get("argv"), source=current.get("source", LOCAL),
                                   origin_how=current.get("origin_how"), insight=ins, comparison=cmp)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    elif fmt == "png":
        from routemap.gui import geometry
        image = mapview.render_png(
            route, dark=dark_png, title=f"{target} from {_city(route)}", destination=target,
            provenance=f"{DISPLAY_NAME} {VERSION} \u00b7 {report.stamp(when)} \u00b7 "
                       f"{label or current.get('source', '')} · {geometry.ATTRIBUTION} · "
                       "GeoNames CC BY 4.0" + (" · IP Geolocation by DB-IP" if mapview.uses_dbip(route) else ""),
            quiet_ms=settings.rtt_quiet_ms, hot_ms=settings.rtt_hot_ms,
            ghost=(cmp or {}).get("old_route"),
            marks={int(k): v for k, v in ((cmp or {}).get("new_marks") or {}).items()} or None)
        if not image.save(path, "PNG"):
            raise OSError(f"could not write {path}")
    elif fmt == "pdf":
        report.write_pdf(path, route, target=target, trace_text=current.get("trace_text", ""),
                         tool_label=label, origin_how=current.get("origin_how"),
                         source=current.get("source", LOCAL), when=when, include_trace=include_trace,
                         insight=ins, comparison=cmp, quiet_ms=settings.rtt_quiet_ms,
                         hot_ms=settings.rtt_hot_ms, origin_cc=_origin_cc_of(route))
    else:
        raise ValueError(f"unknown export format {fmt!r}")


def _origin_cc_of(route: dict) -> str | None:
    from routemap_engine import cities as _cities
    origin = route.get("origin") or {}
    if origin.get("lat") is None:
        return None
    return (_cities.nearest(origin["lat"], origin["lon"], max_km=400) or {}).get("cc")


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
    app.setApplicationVersion(VERSION)
    icon_path = os.path.join(os.path.dirname(__file__), "data", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    return app


def run_gui(target: str | None = None, origin_override: tuple | None = None) -> int:
    app = make_app()
    service.startup()
    settings = config.load_settings()
    from routemap.gui import theme
    theme.apply(app, settings.theme)
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
