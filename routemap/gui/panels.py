"""Smaller pieces of the main window: unplaced hops, paths, the reverse trace, live
output, history, progress."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QHeaderView, QLabel, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from routemap.gui import theme
from routemap.gui.text import plain


class UnplacedPanel(QWidget):
    """Collapsible list of hops with no location, each with its reason."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.toggle = QToolButton(self)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.RightArrow)
        self.toggle.setCheckable(True)
        self.toggle.setAutoRaise(True)
        self.toggle.toggled.connect(self._expand)
        self.list = QTreeWidget(self)
        self.list.setColumnCount(3)
        self.list.setHeaderLabels(["Hop", "Answered from", "Why it is not on the map"])
        self.list.setRootIsDecorated(False)
        self.list.setWordWrap(True)
        self.list.setUniformRowHeights(False)
        self.list.setAlternatingRowColors(True)
        self.list.setMaximumHeight(190)
        header = self.list.header()
        header.setStretchLastSection(True)
        self.list.setColumnWidth(0, 44)
        self.list.setColumnWidth(1, 150)
        self.list.hide()
        layout.addWidget(self.toggle)
        layout.addWidget(self.list)
        self.set_hops([])

    def _expand(self, on: bool):
        self.toggle.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.list.setVisible(on)

    def set_hops(self, hops: list[dict]):
        unplaced = [h for h in hops if h.get("lat") is None]
        self.list.clear()
        for hop in unplaced:
            reason = hop.get("reason") or "no source could place it"
            details = hop.get("annotation_details") or []
            if details:
                # The annotation explains the reason better than the reason
                # does ("the destination is not answering ICMP" beats "the hop
                # did not answer"), so it leads.
                reason = details[0].split(": ", 1)[-1]
                reason = reason[:1].upper() + reason[1:]
            else:
                reason = reason[:1].upper() + reason[1:]
            who = hop.get("hostname") or hop.get("address") or "no answer"
            item = QTreeWidgetItem([str(hop["hop"]), who, reason])
            item.setTextAlignment(0, Qt.AlignRight | Qt.AlignTop)
            item.setToolTip(2, "<br>".join(html.escape(d) for d in details) or html.escape(reason))
            self.list.addTopLevelItem(item)
        self.toggle.setText(f"Unplaced hops ({len(unplaced)})" if unplaced
                            else "Unplaced hops (none)")
        self.toggle.setEnabled(bool(unplaced))
        if not unplaced:
            self.toggle.setChecked(False)

    def expand(self, on: bool = True):
        self.toggle.setChecked(on)


class _Collapsible(QWidget):
    """A toggle that opens a tree below it, like the unplaced hops."""

    def __init__(self, headers: list[str], widths: list[int], parent=None, height: int = 190):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.toggle = QToolButton(self)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.RightArrow)
        self.toggle.setCheckable(True)
        self.toggle.setAutoRaise(True)
        self.toggle.toggled.connect(self._expand)
        self.note = QLabel(self)
        self.note.setWordWrap(True)
        self.note.setTextFormat(Qt.RichText)
        self.list = QTreeWidget(self)
        self.list.setColumnCount(len(headers))
        self.list.setHeaderLabels(headers)
        self.list.setRootIsDecorated(False)
        self.list.setAlternatingRowColors(True)
        self.list.setMaximumHeight(height)
        self.list.header().setStretchLastSection(True)
        for i, w in enumerate(widths):
            self.list.setColumnWidth(i, w)
        self.list.hide()
        self.note.hide()
        layout.addWidget(self.toggle)
        layout.addWidget(self.note)
        layout.addWidget(self.list)

    def _expand(self, on: bool):
        self.toggle.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.list.setVisible(on)
        self.note.setVisible(on and bool(self.note.text()))

    def expand(self, on: bool = True):
        self.toggle.setChecked(on)


class PathsPanel(_Collapsible):
    """The paths of a path discovery (0.4.0): one row each, with its share of
    the flows, where it differs, and its own latency and loss to the target.
    Choosing a row shows that path alone on the map."""

    pathSelected = Signal(object)        # a path id, or None for all

    def __init__(self, parent=None):
        super().__init__(["Path", "Flows", "Differs at", "RTT to target", "Loss to target"],
                         [52, 72, 220, 100], parent)
        self.list.itemSelectionChanged.connect(self._selected)
        self.setAccessibleName("Paths")
        self.set_paths(None, [])

    def _selected(self):
        items = self.list.selectedItems()
        self.pathSelected.emit(items[0].data(0, Qt.UserRole) if items else None)

    def set_paths(self, discovery: dict | None, hops: list[dict]):
        self.list.clear()
        paths = (discovery or {}).get("paths") or []
        self.setVisible(bool(discovery))
        if not discovery:
            return
        main = {h.get("hop"): h.get("address") for h in hops}
        total = sum(len(p.get("flows") or []) for p in paths) or 1
        for index, p in enumerate(paths):
            differs = []
            for h in p.get("located") or []:
                if h.get("address") and h.get("address") != main.get(h.get("hop")):
                    differs.append(f"hop {h['hop']}: " + (h.get("place") or h.get("hostname") or h["address"]))
            loss, sent, lost = p.get("loss_pct"), p.get("sent") or 0, p.get("lost") or 0
            rtt = p.get("rtt_to_target_ms")
            item = QTreeWidgetItem([
                p.get("id") or "?", f"{len(p.get('flows') or [])} of {total}",
                "; ".join(differs) or ("the route shown" if len(paths) > 1 else "one path"),
                "" if rtt is None else f"{rtt:.1f} ms",
                "" if loss is None else f"{loss:g}% ({lost} of {sent})"])
            item.setData(0, Qt.UserRole, p.get("id"))
            item.setForeground(0, theme.path_color(theme.current(), index))
            for col in (1, 3, 4):
                item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
            self.list.addTopLevelItem(item)
        word = "path" if len(paths) == 1 else "paths"
        self.toggle.setText(f"Paths: at least {len(paths)} {word}")
        notes = ["“At least”: some load balancers do not spread ICMP probes, so a path can stay hidden."]
        if discovery.get("per_packet_hops"):
            notes.append("Per-packet balancing at hop " + ", ".join(str(h) for h in discovery["per_packet_hops"])
                         + ": every packet may take another router there, so it does not make paths.")
        if discovery.get("stopped_by") == "budget":
            notes.append(f"Stopped at the probe budget ({discovery.get('probes_sent')} probes); "
                         "more paths may exist.")
        self.note.setText("<span style='color:gray'>" + "<br>".join(html.escape(n) for n in notes) + "</span>")
        self.toggle.setEnabled(True)


class ReversePanel(_Collapsible):
    """A reverse trace beside the forward one (0.4.0), aligned by network:
    forward on the left, reverse on the right read from you to the target,
    tinted where the two directions take different routers."""

    def __init__(self, parent=None):
        super().__init__(["Forward (you to target)", "Network", "Reverse (read you to target)"],
                         [190, 90], parent, height=260)
        self.setAccessibleName("Reverse trace")
        self.set_comparison(None, None)

    @staticmethod
    def _cell(seg: dict | None) -> str:
        if not seg:
            return "(no hop)"
        hops = seg["hops"]
        n = (f"{hops[0]['hop']}" if len(hops) == 1 else f"{hops[0]['hop']}-{hops[-1]['hop']}")
        return f"{n}  {seg.get('place') or hops[0].get('address') or ''}"

    def set_comparison(self, reverse: dict | None, comparison: dict | None):
        self.list.clear()
        self.setVisible(bool(reverse))
        if not reverse:
            return
        from PySide6.QtGui import QColor
        tint = QColor(theme.diff_color(theme.current(), "moved"))     # a copy: the palette's own stays opaque
        tint.setAlpha(45)
        for row in (comparison or {}).get("rows") or []:
            seg = row["forward"] or row["reverse"]
            asn = seg.get("asn") if seg else None
            item = QTreeWidgetItem([self._cell(row["forward"]), f"AS{asn}" if asn else "",
                                    self._cell(row["reverse"])])
            if not row["same"]:
                for col in range(3):
                    item.setBackground(col, tint)
                item.setToolTip(0, "The two directions take different routers here.")
            self.list.addTopLevelItem(item)
        probe = reverse.get("probe") or {}
        msm = reverse.get("measurement_id")
        self.toggle.setText("Reverse trace: " + ("the same path both ways" if not (comparison or {}).get("differs")
                                                 else "the directions differ"))
        self.note.setText(
            f"<span style='color:gray'>{html.escape((comparison or {}).get('summary') or '')}<br>"
            f"RIPE Atlas probe #{html.escape(str(probe.get('id')))}"
            + (f" in AS{html.escape(str(probe.get('asn')))}" if probe.get("asn") else "")
            + (f", {html.escape(str(probe.get('country')))}" if probe.get("country") else "")
            + (f" · <a href='https://atlas.ripe.net/measurements/{int(msm)}/'>measurement {int(msm)}</a>"
               if msm else "")
            + " · different routes each way are normal on the Internet.</span>")
        self.note.setOpenExternalLinks(True)


class LiveOutput(QWidget):
    """The tool's own output, line by line. Collapsed by default under the table."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.toggle = QToolButton(self)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.RightArrow)
        self.toggle.setCheckable(True)
        self.toggle.setAutoRaise(True)
        self.toggle.toggled.connect(self._expand)
        layout.addWidget(self.toggle)
        self.body = QWidget(self)
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(4)
        layout.addWidget(self.body)
        self.heading = QLabel(self.body)
        self.heading.setTextFormat(Qt.RichText)
        self.text = QPlainTextEdit(self.body)
        self.text.setMinimumHeight(140)
        self.text.setMaximumHeight(240)
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        mono.setPixelSize(13)
        self.text.setFont(mono)
        body.addWidget(self.heading)
        body.addWidget(self.text, 1)
        self.lines = 0
        self.body.hide()
        self._label()

    def _expand(self, on: bool):
        self.toggle.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.body.setVisible(on)

    def _label(self):
        self.toggle.setText(f"Tool output ({self.lines} lines)" if self.lines else "Tool output")

    def start(self, argv: list[str]):
        import os
        parts = [os.path.basename(argv[0])] + list(argv[1:]) if argv else []
        self.heading.setText(f"<code>{html.escape(' '.join(parts))}</code>")
        self.text.clear()
        self.lines = 0
        self._label()

    def set_text(self, text: str, argv: list[str] | None = None):
        self.start(argv or [])
        for line in (text or "").splitlines():
            self.append(line)

    def append(self, line: str):
        self.text.appendPlainText(line)
        self.lines += 1
        self._label()


class HistoryPanel(QWidget):
    """The last traces, newest first. Click to reopen; clearable."""

    opened = Signal(int)
    cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.list = QListWidget(self)
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setSpacing(3)
        self.list.setAlternatingRowColors(True)
        self.list.itemActivated.connect(lambda item: self.opened.emit(self.list.row(item)))
        self.note = plain("", self)
        self.note.setWordWrap(True)
        self.clear_button = QPushButton("Clear history", self)
        self.clear_button.clicked.connect(self.cleared)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.note)
        layout.addWidget(self.clear_button)

    def set_entries(self, entries: list[dict], enabled: bool = True, limit: int = 50):
        self.list.clear()
        for entry in entries:
            item = QListWidgetItem(f"{entry['target']}\n{entry['when']} · "
                                   f"{entry['hops']} hops, {entry['placed']} placed")
            item.setToolTip(html.escape(str(entry.get("tool") or "")))
            self.list.addItem(item)
        if enabled:
            self.note.setText(f"Last {limit} traces, kept in your config folder.")
        else:
            self.note.setText("History is off in Settings. Nothing is stored.")
        self.clear_button.setEnabled(enabled and bool(entries))


class SourceStatus(QWidget):
    """Per-source progress in the status bar: PTR, Hoiho, IP database."""

    LABELS = (("trace", "Trace"), ("reverse-dns", "PTR"), ("hoiho", "Hoiho"), ("ip-db", "IP db"))
    MARKS = {"waiting": "•", "started": "…", "done": "✓", "timeout": "timed out",
             "failed": "failed", "off": "off"}

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.labels = {}
        for key, name in self.LABELS:
            label = QLabel(self)
            label.setTextFormat(Qt.RichText)
            self.labels[key] = (label, name)
            layout.addWidget(label)
        self.reset()

    def reset(self):
        self.states = {}
        for key in self.labels:
            self.set_state(key, "waiting")

    def finish(self):
        """Anything still waiting or running when the result arrives is done;
        a timeout, a failure or "off" stays visible."""
        for key in self.labels:
            if self.states.get(key) in (None, "waiting", "started"):
                self.set_state(key, "done")

    def set_state(self, source: str, state: str, detail: str | None = None):
        if source not in self.labels:
            return
        label, name = self.labels[source]
        self.states[source] = state
        mark = detail if (detail and state == "started") else self.MARKS.get(state, state)
        muted = theme.current().overlay_muted.name()
        color = {"done": theme.current().sources["site-code"].name(),
                 "timeout": "#c0392b", "failed": "#c0392b"}.get(state, muted)
        label.setText(f"<span style='color:{muted}'>{name}</span> "
                      f"<span style='color:{color}'>{html.escape(mark)}</span>")
