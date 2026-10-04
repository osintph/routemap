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
    route_quiet: QColor       # an RTT step under the quiet threshold
    route_warm: QColor        # just over it
    route_hot: QColor         # at or over the hot threshold
    space: QColor             # behind the globe
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
    route_quiet=QColor("#7d8a98"),
    route_warm=QColor("#d99a2b"),
    route_hot=QColor("#c2410c"),
    space=QColor("#f3f5f7"),
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
    route_quiet=QColor("#8796a5"),
    route_warm=QColor("#f0b44c"),
    route_hot=QColor("#ff7a3d"),
    space=QColor("#080d13"),
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


def mix(a: QColor, b: QColor, t: float) -> QColor:
    """*a* to *b* at *t* in [0, 1]."""
    t = max(0.0, min(1.0, t))
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def step_color(palette: Palette, cls: str, intensity: float) -> QColor:
    """The line colour for an RTT step class from routemap_engine.osint."""
    if cls == "quiet":
        return palette.route_quiet
    if cls in ("warm", "hot"):
        return mix(palette.route_warm, palette.route_hot, intensity)
    return palette.route


# What a comparison's marks mean, in the words the legend and tables use.
DIFF_LABELS = {
    "added": "New in this run",
    "moved": "Placed elsewhere this run",
    "removed": "Gone since the earlier run",
    "rtt": "RTT changed by 20 ms or more",
    "asn": "Different network (AS) at the same place",
    "silent": "Did not answer this run",
}


def diff_color(palette: Palette, mark: str) -> QColor:
    return {"added": palette.route_warm, "moved": palette.route_warm, "removed": palette.route_gap,
            "rtt": palette.route_hot, "asn": palette.sources["hoiho"],
            "silent": palette.route_gap}.get(mark, palette.route)
