"""Labels show text, not markup, unless this module's caller built the markup
(hardening 2). A QLabel left at Qt.AutoText guesses from its content, so a
value from a file or an online answer could switch it to rich text: every label
in the main window says which it is, and every value put into markup goes
through esc()."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget


def esc(value) -> str:
    """Any value, as text that markup shows literally."""
    return html.escape(str(value if value is not None else ""))


def plain(text: str = "", parent: QWidget | None = None) -> QLabel:
    """A label that never interprets its text."""
    label = QLabel(text, parent)
    label.setTextFormat(Qt.PlainText)
    return label


def markup(text: str = "", parent: QWidget | None = None) -> QLabel:
    """A label for markup the caller built from esc()'d values. Opens no links."""
    label = QLabel(text, parent)
    label.setTextFormat(Qt.RichText)
    label.setOpenExternalLinks(False)
    return label
