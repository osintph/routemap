"""
Continuous mode in the window: the controls bar, the ping plot, the path changes.

All three only draw what routemap.live.snapshot() produced; the session runs
in the engine (routemap_engine.watch) on a worker thread.

The plot shows the selected hop (solid) and the destination (dashed) over the
last 5 minutes by default; 1 to 4 choose 5 minutes, 15 minutes, 1 hour or the
whole session. Lost probes are marks on the baseline and a path change is a
vertical rule, so nothing depends on colour alone. Colours come from the
chosen RTT palette. The plot's accessible description is a sentence about the
range shown, and the bar announces pauses, path changes and the end of a
session to screen readers; live numbers are read when a row is focused, not
every second.
"""
from __future__ import annotations

import html
import time

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAccessible, QAccessibleEvent, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from routemap import live as live_mod
from routemap.gui import theme

RANGES = ((300, "5 min"), (900, "15 min"), (3600, "1 hour"), (None, "whole session"))


def _clock(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _announce(widget: QWidget, text: str) -> None:
    """Tell a screen reader, politely: the widget's name changes and the
    accessibility layer is told so."""
    widget.setAccessibleName(text)
    try:
        QAccessible.updateAccessibility(QAccessibleEvent(widget, QAccessible.Event.NameChanged))
    except Exception:  # noqa: BLE001 - no accessibility backend: nothing to tell
        pass


class LiveBar(QWidget):
    pauseToggled = Signal()
    stopClicked = Signal()
    resetClicked = Signal()
    exportClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.state = QLabel()
        self.state.setTextFormat(Qt.PlainText)
        self.state.setAccessibleName("Continuous trace")
        self.pause = QPushButton("Pause")
        self.pause.setToolTip("Pause or resume (P)")
        self.stop = QPushButton("Stop")
        self.reset = QPushButton("Reset counters")
        self.reset.setToolTip("Start the statistics again; the map and the path changes stay")
        self.export = QPushButton("Export…")
        self.export.setVisible(False)
        self.limits = QLabel()
        self.limits.setProperty("muted", True)
        self.limits.setTextFormat(Qt.PlainText)
        for w in (self.state, self.pause, self.stop, self.reset, self.export):
            row.addWidget(w)
        row.addWidget(self.limits, 1)
        self.pause.clicked.connect(self.pauseToggled)
        self.stop.clicked.connect(self.stopClicked)
        self.reset.clicked.connect(self.resetClicked)
        self.export.clicked.connect(self.exportClicked)
        self._said = ""

    def show_state(self, snap: dict, running: bool) -> None:
        elapsed = (snap.get("now") or time.time()) - (snap.get("started") or time.time())
        cycles = snap.get("cycles", 0)
        if not running:
            why = {"duration": " (reached its time limit)", "count": " (reached its cycle count)",
                   "error": " (an error stopped it)"}.get(snap.get("stopped_by"), "")
            text = f"Stopped{why} · {cycles} cycles · {_clock(elapsed)}"
        elif snap.get("paused"):
            text = f"Paused at cycle {cycles} · {_clock(elapsed)}"
        else:
            text = f"Live · cycle {cycles} · {_clock(elapsed)}"
        self.state.setText(text)
        self.pause.setText("Resume" if snap.get("paused") else "Pause")
        self.pause.setVisible(running)
        self.stop.setVisible(running)
        self.reset.setVisible(running)
        self.export.setVisible(not running)
        interval = snap.get("interval") or 1.0
        limit = _clock(snap.get("duration") or 3600)
        self.limits.setText(f"one probe per hop every {interval:g} s · stops at {limit}")
        # Announce only what changed in kind, not the ticking clock.
        said = "stopped" if not running else "paused" if snap.get("paused") else "live"
        if said != self._said:
            _announce(self.state, {"live": "Continuous trace running", "paused": "Continuous trace paused",
                                   "stopped": f"Continuous trace {text}"}[said])
            self._said = said


class PingPlot(QWidget):
    """RTT over time for the selected hop and the destination."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("Ping plot")
        self.snap: dict | None = None
        self.hop: int | None = None
        self.range_index = 0
        self.with_destination = True    # the PDF draws one hop per plot, on its own scale
        self.printed = False            # in a PDF: only this hop's changes, no key hint

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(600, 170)

    def set_data(self, snap: dict | None, hop: int | None = None) -> None:
        self.snap = snap
        if hop is not None:
            self.hop = hop
        self.setAccessibleDescription(self.summary())
        self.update()

    def destination(self) -> int | None:
        if not self.snap:
            return None
        return self.snap.get("reached_hop") or (self.snap["hops"][-1]["hop"] if self.snap.get("hops") else None)

    def series(self, hop: int | None) -> list[tuple[float, float | None]]:
        if not self.snap or hop is None:
            return []
        points = self.snap.get("live", {}).get(hop) or []
        span = RANGES[self.range_index][0]
        if span is not None and points:
            end = points[-1][0]
            points = [p for p in points if p[0] >= end - span]
        return points

    def summary(self) -> str:
        hop, dst = self.hop, self.destination()
        parts = []
        for name, n in (("hop", hop), ("destination", dst)):
            pts = self.series(n)
            got = [r for _, r in pts if r is not None]
            if not pts:
                continue
            lost = len(pts) - len(got)
            if got:
                parts.append(f"{'Hop ' + str(n) if name == 'hop' else 'Destination'}: {len(pts)} probes, "
                             f"{min(got):.0f} to {max(got):.0f} ms, {lost} lost")
            else:
                parts.append(f"{'Hop ' + str(n) if name == 'hop' else 'Destination'}: {len(pts)} probes, all lost")
        rng = RANGES[self.range_index][1]
        return (f"Last {rng}. " if self.range_index < 3 else "Whole session. ") + ("; ".join(parts) or "No data yet.")

    def keyPressEvent(self, event):
        k = event.key()
        if Qt.Key_1 <= k <= Qt.Key_4:
            self.range_index = k - Qt.Key_1
            self.setAccessibleDescription(self.summary())
            self.update()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = theme.current()
        p.fillRect(self.rect(), self.palette().base())
        left, right, top, bottom = 46.0, 10.0, 18.0, 22.0
        w, h = self.width() - left - right, self.height() - top - bottom
        if w <= 10 or h <= 10:
            return
        hop_pts = self.series(self.hop)
        dst_pts = self.series(self.destination()) if (self.with_destination or self.hop is None) \
            and self.destination() != self.hop else []
        allp = hop_pts + dst_pts
        values = [r for _, r in allp if r is not None]
        muted = QColor(pal.overlay_muted)
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
        p.setFont(font)
        if not allp:
            p.setPen(muted)
            p.drawText(self.rect(), Qt.AlignCenter, "The plot fills as the cycles come in.")
            return
        span = RANGES[self.range_index][0]
        t1 = max(t for t, _ in allp)
        # A fixed range is always that wide, so a sleep inside it shows as a gap.
        t0 = t1 - span if span is not None else min(t for t, _ in allp)
        t1 = max(t1, t0 + 1)
        lo = min(values) if values else 0.0
        hi = max(values) if values else 1.0
        pad = max(2.0, (hi - lo) * 0.1)
        lo, hi = max(0.0, lo - pad), hi + pad

        def x(t):
            return left + w * (t - t0) / (t1 - t0)

        def y(ms):
            return top + h * (1 - (ms - lo) / (hi - lo))
        grid = QColor(pal.border)
        for i in range(4):
            ms = lo + (hi - lo) * i / 3
            p.setPen(QPen(grid, 1))
            p.drawLine(QPointF(left, y(ms)), QPointF(left + w, y(ms)))
            p.setPen(muted)
            p.drawText(QRectF(0, y(ms) - 8, left - 6, 16), Qt.AlignRight | Qt.AlignVCenter, f"{ms:.0f}")
        p.drawText(QRectF(left, top + h + 4, w, 16), Qt.AlignLeft, f"-{_clock(t1 - t0)}")
        p.drawText(QRectF(left, top + h + 4, w, 16), Qt.AlignRight, "now")
        started = (self.snap or {}).get("started") or 0
        # Sleep or suspend: shaded, labelled, never drawn as loss.
        shade = QColor(pal.border)
        shade.setAlpha(110)
        for g in (self.snap or {}).get("gaps") or []:
            if isinstance(g.get("from"), (int, float)) and isinstance(g.get("to"), (int, float)):
                a, b = max(t0, g["from"] - started), min(t1, g["to"] - started)
                if b > a:
                    p.fillRect(QRectF(x(a), top, max(1.0, x(b) - x(a)), h), shade)
                    p.setPen(muted)
                    p.drawText(QRectF(x(a), top + 2, max(40.0, x(b) - x(a)), 14), Qt.AlignHCenter, "gap")
        # Path changes inside the range.
        change_pen = QPen(QColor(pal.route), 1, Qt.DashLine)
        for c in (self.snap or {}).get("changes") or []:
            if self.printed and c.get("hop") != self.hop:
                continue
            at = c.get("at")
            if isinstance(at, (int, float)):
                tc = at - started
                if t0 <= tc <= t1:
                    p.setPen(change_pen)
                    p.drawLine(QPointF(x(tc), top), QPointF(x(tc), top + h))
                    p.drawText(QPointF(x(tc) + 3, top + 10), f"cycle {c.get('cycle')}")

        # A pause or a gap: samples further apart than this are not joined.
        gap_after = 3 * float((self.snap or {}).get("interval") or 1.0)

        def line(points, color, style, width):
            path, drawing, last_t = QPainterPath(), False, None
            for t, r in points:
                if r is None:
                    drawing = False
                    continue
                if last_t is not None and t - last_t > gap_after:
                    drawing = False
                last_t = t
                pt = QPointF(x(t), y(min(hi, r)))
                if drawing:
                    path.lineTo(pt)
                else:
                    path.moveTo(pt)
                    drawing = True
            pen = QPen(color, width, style)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        line(dst_pts, QColor(pal.route_quiet), Qt.DashLine, 1.2)
        line(hop_pts, QColor(pal.route_warm), Qt.SolidLine, 1.8)
        # Lost probes: marks on the baseline.
        lost_color = QColor(pal.route_hot)
        for t, r in hop_pts + dst_pts:
            if r is None:
                p.fillRect(QRectF(x(t) - 1.5, top + h - 6, 3, 6), lost_color)
        p.setPen(QColor(pal.overlay_fg))
        dst = self.destination()
        label = (f"hop {self.hop} (solid)" if self.hop is not None and self.hop != dst else "")
        if dst_pts or self.hop == dst:
            label += (" · " if label else "") + f"destination, hop {dst}" + (" (dashed)" if dst_pts else "")
        label += " · ms · marks: lost probes"
        hint = "" if self.printed else " (keys 1 to 4)"
        p.drawText(QPointF(left + 4, top - 5), f"{label} · {RANGES[self.range_index][1]}{hint}")


class ChangeList(QLabel):
    """Path changes and gaps, newest last, as plain sentences."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.RichText)
        self.setWordWrap(True)
        self.setAccessibleName("Path changes")
        self._count = 0

    def set_data(self, snap: dict | None) -> None:
        changes = (snap or {}).get("changes") or []
        gaps = (snap or {}).get("gaps") or []
        lines = []
        for c in changes[-8:]:
            at = c.get("at")
            when = time.strftime("%H:%M:%S", time.localtime(at)) if isinstance(at, (int, float)) else ""
            lines.append(html.escape(f"{when} {live_mod.describe_change(c)}".strip()))
        for g in gaps[-3:]:
            if isinstance(g.get("from"), (int, float)):
                a = time.strftime("%H:%M:%S", time.localtime(g["from"]))
                b = time.strftime("%H:%M:%S", time.localtime(g["to"]))
                lines.append(html.escape(f"Gap {a} to {b}: the computer slept or the app was suspended; "
                                         "not counted as loss."))
        head = f"<b>Path changes: {len(changes)}</b>" if changes else "<b>Path changes: none</b>"
        self.setText(head + ("<br>" + "<br>".join(lines) if lines else ""))
        if len(changes) > self._count:
            _announce(self, "Path change. " + live_mod.describe_change(changes[-1]))
        self._count = len(changes)
