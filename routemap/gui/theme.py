"""
Colours, fonts and labels the window shares, in light and dark.

One look on every platform (0.2.0): the Fusion style, our own palettes with
one accent colour, and the bundled IBM Plex Sans at a fixed pixel size. The
platform's default style made the same build look different on Windows and
macOS (accent, buttons, fonts). Only the native window frame and the menu bar
position still differ.

The theme is System (follow the OS, live), Light or Dark: Settings > Map, and
View > Theme. It applies to the window, the map and the exports.
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


THEMES = ("system", "light", "dark")
_choice = "system"
FONT_PX = 13
ACCENT = {"light": "#b4530a", "dark": "#f0a440"}


def choice() -> str:
    return _choice


def is_dark() -> bool:
    if _choice == "dark":
        return True
    if _choice == "light":
        return False
    app = QGuiApplication.instance()
    if app is None:
        return False
    return app.styleHints().colorScheme() == Qt.ColorScheme.Dark


def _load_fonts() -> str:
    """Register the bundled IBM Plex fonts once; return the family name."""
    from importlib import resources
    from PySide6.QtGui import QFontDatabase
    family = "IBM Plex Sans"
    if family in QFontDatabase.families():
        return family
    folder = resources.files("routemap.gui").joinpath("data/fonts")
    for entry in folder.iterdir():
        if entry.name.endswith(".ttf"):
            QFontDatabase.addApplicationFontFromData(entry.read_bytes())
    return family if family in QFontDatabase.families() else QGuiApplication.font().family()


def _palette(dark: bool):
    from PySide6.QtGui import QPalette
    c = (lambda x: QColor(x))
    if dark:
        win, base, alt, text, mid, btn, disabled = "#141c25", "#0f161e", "#18222d", "#e6ebf0", "#2a3643", "#1d2732", "#6b7885"
    else:
        win, base, alt, text, mid, btn, disabled = "#f4f6f8", "#ffffff", "#f1f4f7", "#1b2633", "#cdd5dd", "#ffffff", "#9aa6b2"
    accent = c(ACCENT["dark" if dark else "light"])
    pal = QPalette()
    for group in (QPalette.Active, QPalette.Inactive):
        pal.setColor(group, QPalette.Window, c(win))
        pal.setColor(group, QPalette.WindowText, c(text))
        pal.setColor(group, QPalette.Base, c(base))
        pal.setColor(group, QPalette.AlternateBase, c(alt))
        pal.setColor(group, QPalette.Text, c(text))
        pal.setColor(group, QPalette.Button, c(btn))
        pal.setColor(group, QPalette.ButtonText, c(text))
        pal.setColor(group, QPalette.ToolTipBase, c(base))
        pal.setColor(group, QPalette.ToolTipText, c(text))
        pal.setColor(group, QPalette.PlaceholderText, c(disabled))
        pal.setColor(group, QPalette.Mid, c(mid))
        pal.setColor(group, QPalette.Highlight, accent)
        pal.setColor(group, QPalette.HighlightedText, c("#ffffff" if not dark else "#10161d"))
        pal.setColor(group, QPalette.Link, accent)
        pal.setColor(group, QPalette.Accent, accent)
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, c(disabled))
    pal.setColor(QPalette.Disabled, QPalette.Base, c(win))
    return pal


def stylesheet(dark: bool) -> str:
    accent = ACCENT["dark" if dark else "light"]
    edge = "#2a3643" if dark else "#cdd5dd"
    hover = "#222e3a" if dark else "#eef2f6"
    on_accent = "#10161d" if dark else "#ffffff"
    return (f"QPushButton {{ padding: 5px 14px; border: 1px solid {edge}; border-radius: 6px; }}"
            f"QPushButton:hover {{ background: {hover}; }}"
            f"QPushButton:default {{ background: {accent}; color: {on_accent}; border-color: {accent};"
            f" font-weight: 600; }}"
            f"QPushButton:disabled {{ color: palette(placeholder-text); }}"
            f"QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ padding: 4px 6px; border: 1px solid {edge};"
            f" border-radius: 5px; }}"
            f"QLineEdit:focus {{ border-color: {accent}; }}"
            f"QHeaderView::section {{ padding: 4px 6px; border: 0; border-bottom: 1px solid {edge}; }}")


def apply(app, theme: str = "system") -> None:
    """Set the one app look: Fusion, our palette, the bundled font, for *theme*."""
    global _choice
    _choice = theme if theme in THEMES else "system"
    from PySide6.QtGui import QFont
    style = app.setStyle("Fusion")
    # What parity checks read: the stylesheet below wraps the style object.
    app.setProperty("routemapStyle", style.name() if style is not None else "")
    scheme = {"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(_choice, Qt.ColorScheme.Unknown)
    try:
        app.styleHints().setColorScheme(scheme)        # Qt 6.8+: also tells the OS window frame
    except AttributeError:
        pass
    font = QFont(_load_fonts())
    font.setPixelSize(FONT_PX)
    app.setFont(font)
    # macOS gives some widget classes their own smaller system font, which the
    # application font does not override; set ours on each of them.
    for cls in ("QToolButton", "QPushButton", "QLabel", "QHeaderView", "QTableView", "QAbstractItemView",
                "QComboBox", "QLineEdit", "QMenu", "QMenuBar", "QTabBar", "QCheckBox", "QRadioButton",
                "QGroupBox", "QStatusBar", "QTipLabel", "QSpinBox", "QDoubleSpinBox", "QPlainTextEdit",
                "QTextBrowser", "QListWidget"):
        app.setFont(font, cls)
    dark = is_dark()
    app.setPalette(_palette(dark))
    app.setStyleSheet(stylesheet(dark))


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
