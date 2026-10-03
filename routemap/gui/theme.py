"""
Colours and labels the window shares, in light and dark.

The widgets are the platform's own (no forced style), so only what we draw
ourselves is themed here: the map, the markers, the legend and the overlays.
The scheme follows the OS through Qt's style hints and switches live.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication

# What each source label means, in the words the table and legend use.
SOURCE_LABELS = {
    "hoiho": "Hostname rule (CAIDA Hoiho)",
    "site-code": "Carrier site code",
    "ip-db": "IP database (fallback)",
    "local": "Local / ISP network",
    "unresolved": "Not placed",
}
SOURCE_SHORT = {
    "hoiho": "hoiho",
    "site-code": "site-code",
    "ip-db": "ip-db",
    "local": "local",
    "unresolved": "unresolved",
}


@dataclass(frozen=True)
class Palette:
    dark: bool
    ocean: QColor
    land: QColor
    coast: QColor
    border: QColor
    route: QColor
    route_gap: QColor
    marker_text: QColor
    marker_ring: QColor
    origin: QColor
    overlay_bg: QColor
    overlay_fg: QColor
    overlay_muted: QColor
    sources: dict


LIGHT = Palette(
    dark=False,
    ocean=QColor("#e6edf3"),
    land=QColor("#fbfaf7"),
    coast=QColor("#b9c4ce"),
    border=QColor("#d3d9df"),
    route=QColor("#24364b"),
    route_gap=QColor("#8a97a6"),
    marker_text=QColor("#ffffff"),
    marker_ring=QColor("#ffffff"),
    origin=QColor("#111827"),
    overlay_bg=QColor(255, 255, 255, 232),
    overlay_fg=QColor("#1f2933"),
    overlay_muted=QColor("#5f6b78"),
    sources={
        "hoiho": QColor("#2f6fdf"),
        "site-code": QColor("#0f8a7e"),
        "ip-db": QColor("#c9730a"),
        "local": QColor("#6b7480"),
        "unresolved": QColor("#a3abb5"),
    },
)

DARK = Palette(
    dark=True,
    ocean=QColor("#0e151d"),
    land=QColor("#1b2530"),
    coast=QColor("#33414f"),
    border=QColor("#2a3643"),
    route=QColor("#c9d6e3"),
    route_gap=QColor("#5d6b79"),
    marker_text=QColor("#0e151d"),
    marker_ring=QColor("#0e151d"),
    origin=QColor("#f2f4f7"),
    overlay_bg=QColor(22, 31, 41, 236),
    overlay_fg=QColor("#e6ebf0"),
    overlay_muted=QColor("#9aa7b4"),
    sources={
        "hoiho": QColor("#6fa0ff"),
        "site-code": QColor("#3cc3b4"),
        "ip-db": QColor("#f0a440"),
        "local": QColor("#9aa4ae"),
        "unresolved": QColor("#5d6b79"),
    },
)


def is_dark() -> bool:
    app = QGuiApplication.instance()
    if app is None:
        return False
    return app.styleHints().colorScheme() == Qt.ColorScheme.Dark


def current() -> Palette:
    return DARK if is_dark() else LIGHT
