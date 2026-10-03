"""Smaller pieces of the main window: unplaced hops, live output, history, progress."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QHeaderView, QLabel, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from routemap.gui import theme


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


class LiveOutput(QWidget):
    """The tool's own output, line by line, while the trace runs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.heading = QLabel(self)
        self.heading.setTextFormat(Qt.RichText)
        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        mono.setPointSizeF(max(10.0, mono.pointSizeF()))
        self.text.setFont(mono)
        layout.addWidget(self.heading)
        layout.addWidget(self.text, 1)

    def start(self, argv: list[str]):
        command = " ".join(argv)
        self.heading.setText(f"<b>Running</b> <code>{html.escape(command)}</code>")
        self.text.clear()

    def append(self, line: str):
        self.text.appendPlainText(line)


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
        self.note = QLabel(self)
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
            item.setToolTip(entry.get("tool", ""))
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
