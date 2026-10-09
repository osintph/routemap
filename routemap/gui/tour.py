"""
The first-run tour: five short cards over the real window, each pointing at one thing.

Shown once, on the first start (Settings.tour_seen); Skip or Done ends it and
Help > Show the Tour brings it back. Each card is a small frame beside the
widget it describes. Keys: Right or Enter for next, Left for back, Esc to
skip. Every card has an accessible name and description, so a screen reader
announces it when it takes focus.

:func:`steps` is Qt-free, so the words (including the platform's menu paths)
are tested without a window.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from routemap.__about__ import DISPLAY_NAME


def settings_path(system: str | None = None) -> str:
    """Where Settings is in the menus: the application menu on macOS."""
    system = system or sys.platform
    return f"{DISPLAY_NAME} › Settings" if system == "darwin" else "Edit › Settings"


def steps(system: str | None = None) -> list[dict]:
    """The cards, in order: {"key", "title", "text", "target"}. ``target`` names
    the MainWindow attribute the card sits beside."""
    where = settings_path(system)
    return [
        {"key": "origin", "title": "Where you are", "target": "origin_label",
         "text": f"{DISPLAY_NAME} starts the route at your origin. It finds it from your network, or "
                 f"you set a city or coordinates in {where} › Origin. It stays on this computer."},
        {"key": "trace", "title": "Run a trace", "target": "target",
         "text": "Type a host name or address and press Trace, or open a saved traceroute with "
                 "File › Open Trace. A trace takes a few seconds."},
        {"key": "map", "title": "Read the map", "target": "map",
         "text": "Each dot is a hop. A line changes colour as the time between two hops grows; grey "
                 f"means a short step. The colours are in {where} › Map."},
        {"key": "table", "title": "Read the table", "target": "table",
         "text": "Source says how each hop was placed. Notes explain numbers that look wrong but are "
                 "not, such as loss that is only a router rate-limiting its replies."},
        {"key": "help", "title": "Settings and Help", "target": "menuBar",
         "text": f"{where} holds your origin, trace tool, sources and RIPE Atlas key. Help has "
                 "privacy, updates, bug reports and this tour again."},
    ]


class Tour(QFrame):
    """The card. Lives as a child of the main window; ``finished`` fires once."""

    finished = Signal()

    def __init__(self, window: QWidget, system: str | None = None):
        super().__init__(window)
        self.window_ = window
        self.cards = steps(system)
        self.index = 0
        self.setObjectName("tourCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setAutoFillBackground(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMaximumWidth(320)
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight: 600")
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.count = QLabel()
        self.count.setProperty("muted", True)
        row = QHBoxLayout()
        self.skip = QPushButton("Skip tour")
        self.back = QPushButton("Back")
        self.next = QPushButton("Next")
        self.next.setDefault(True)
        row.addWidget(self.count)
        row.addStretch(1)
        for b in (self.skip, self.back, self.next):
            row.addWidget(b)
        layout.addWidget(self.title)
        layout.addWidget(self.text)
        layout.addLayout(row)
        self.skip.clicked.connect(self.end)
        self.back.clicked.connect(lambda: self.go(self.index - 1))
        self.next.clicked.connect(lambda: self.go(self.index + 1))
        window.installEventFilter(self)
        self.go(0)

    def target(self) -> QWidget | None:
        name = self.cards[self.index]["target"]
        attr = getattr(self.window_, name, None)
        return attr() if callable(attr) else attr

    def go(self, index: int) -> None:
        if index >= len(self.cards):
            self.end()
            return
        self.index = max(0, index)
        card = self.cards[self.index]
        self.title.setText(card["title"])
        self.text.setText(card["text"])
        self.count.setText(f"{self.index + 1} of {len(self.cards)}")
        self.back.setVisible(self.index > 0)
        self.skip.setVisible(self.index < len(self.cards) - 1)
        self.next.setText("Done" if self.index == len(self.cards) - 1 else "Next")
        self.setAccessibleName(f"Tour, step {self.index + 1} of {len(self.cards)}: {card['title']}")
        self.setAccessibleDescription(card["text"])
        self.adjustSize()
        self.place()
        self.show()
        self.raise_()
        self.setFocus(Qt.OtherFocusReason)

    def place(self) -> None:
        widget = self.target()
        win = self.window_
        if widget is None or not widget.isVisible():
            self.move(24, 48)
            return
        top_left = widget.mapTo(win, QPoint(0, 0))
        x = top_left.x() + 16
        y = top_left.y() + widget.height() + 8
        if y + self.height() > win.height() - 8:
            y = max(8, top_left.y() + 16)
        x = max(8, min(x, win.width() - self.width() - 8))
        self.move(x, y)

    def end(self) -> None:
        self.window_.removeEventFilter(self)
        self.hide()
        self.deleteLater()
        self.finished.emit()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key_Escape:
            self.end()
        elif key in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter):
            self.go(self.index + 1)
        elif key == Qt.Key_Left:
            self.go(self.index - 1)
        else:
            super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.window_ and event.type() == QEvent.Resize:
            self.place()
        return False
