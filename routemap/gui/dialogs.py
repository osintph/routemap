"""Dialogs: settings, export, the RIPE Atlas warning, paste a trace, privacy."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QFrame, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QPlainTextEdit,
                               QPushButton, QRadioButton, QSpinBox, QTabWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from routemap.__about__ import DISPLAY_NAME
from routemap.engine.runner import DEFAULT_FLAGS


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.RichText)
    label.setOpenExternalLinks(True)
    label.setProperty("role", "note")
    font = label.font()
    font.setPointSizeF(font.pointSizeF() * 0.92)
    label.setFont(font)
    label.setStyleSheet("color: palette(placeholder-text);")
    return label


def _rule() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


# ----------------------------------------------------------------- settings ---

class SettingsDialog(QDialog):
    def __init__(self, parent=None, *, origin_label: str = "", tools: dict | None = None,
                 cache_count: int = 0, history_count: int = 0):
        super().__init__(parent)
        self.setWindowTitle(f"{DISPLAY_NAME} Settings")
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._origin_page(origin_label), "Origin")
        self.tabs.addTab(self._trace_page(tools or {}), "Trace")
        self.tabs.addTab(self._sources_page(cache_count), "Sources")
        self.tabs.addTab(self._atlas_page(), "RIPE Atlas")
        self.tabs.addTab(self._privacy_page(history_count), "Privacy")
        layout.addWidget(self.tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _origin_page(self, origin_label: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        current = QLabel(f"<b>Current origin:</b> {origin_label or 'not set'}")
        current.setTextFormat(Qt.RichText)
        layout.addWidget(current)
        layout.addWidget(_note("Every route starts here. It is your machine's location, "
                               "never a server's."))
        layout.addWidget(_rule())

        self.origin_group = QButtonGroup(page)
        self.origin_auto = QRadioButton("From my public IP address")
        self.origin_city = QRadioButton("A city")
        self.origin_coords = QRadioButton("Coordinates")
        self.origin_map = QRadioButton("Picked on the map")
        for i, button in enumerate((self.origin_auto, self.origin_city, self.origin_coords,
                                    self.origin_map)):
            self.origin_group.addButton(button, i)
        self.origin_city.setChecked(True)

        layout.addWidget(self.origin_auto)
        layout.addWidget(_note("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;One lookup of your public IP, "
                               "city level. Approximate; wrong on a VPN or exit node."))
        layout.addWidget(self.origin_city)
        city_row = QHBoxLayout()
        city_row.setContentsMargins(24, 0, 0, 0)
        self.city_search = QLineEdit("Manila")
        self.city_search.setPlaceholderText("Search the bundled city list (offline)")
        city_row.addWidget(self.city_search)
        layout.addLayout(city_row)
        self.city_results = QListWidget()
        self.city_results.setMaximumHeight(92)
        for row in ("Manila, PH", "Manila, AR, US", "Manila, UT, US"):
            self.city_results.addItem(row)
        self.city_results.setCurrentRow(0)
        results_row = QHBoxLayout()
        results_row.setContentsMargins(24, 0, 0, 0)
        results_row.addWidget(self.city_results)
        layout.addLayout(results_row)

        layout.addWidget(self.origin_coords)
        coords = QHBoxLayout()
        coords.setContentsMargins(24, 0, 0, 0)
        self.lat = QDoubleSpinBox()
        self.lat.setRange(-90, 90)
        self.lat.setDecimals(2)
        self.lat.setValue(14.60)
        self.lon = QDoubleSpinBox()
        self.lon.setRange(-180, 180)
        self.lon.setDecimals(2)
        self.lon.setValue(121.00)
        coords.addWidget(QLabel("Latitude"))
        coords.addWidget(self.lat)
        coords.addSpacing(12)
        coords.addWidget(QLabel("Longitude"))
        coords.addWidget(self.lon)
        coords.addStretch(1)
        layout.addLayout(coords)

        layout.addWidget(self.origin_map)
        pick = QHBoxLayout()
        pick.setContentsMargins(24, 0, 0, 0)
        self.pick_button = QPushButton("Pick on the map…")
        pick.addWidget(self.pick_button)
        pick.addStretch(1)
        layout.addLayout(pick)
        layout.addWidget(_rule())
        layout.addWidget(_note("A chosen origin is remembered, and while one is set the public "
                               "IP lookup is skipped entirely. City list: GeoNames, CC BY 4.0."))
        layout.addStretch(1)
        return page

    def _trace_page(self, tools: dict) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.tool = QComboBox()
        names = ["traceroute", "mtr", "tracert"]
        self.tool.addItem("Automatic")
        for name in names:
            status = "installed" if name in tools else "not installed"
            self.tool.addItem(f"{name} ({status})")
            if name not in tools:
                item = self.tool.model().item(self.tool.count() - 1)
                item.setEnabled(False)
        form.addRow("Tool", self.tool)
        form.addRow("", _note("Detected at startup. tracert on Windows; traceroute on macOS "
                              "and Linux; mtr where installed (on macOS mtr needs administrator "
                              "rights, so it is not offered there)."))
        self.flags = {}
        for name in ("traceroute", "mtr", "tracert"):
            edit = QLineEdit(" ".join(DEFAULT_FLAGS[name]))
            mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
            edit.setFont(mono)
            self.flags[name] = edit
            form.addRow(f"{name} flags", edit)
        reset = QPushButton("Restore defaults")
        form.addRow("", reset)
        form.addRow("", _note("Probe types that need administrator rights (traceroute "
                              "<code>-I</code> ICMP, <code>-T</code> TCP) are flagged, not "
                              "escalated: the trace never runs with elevated privileges."))
        self.timeout = QSpinBox()
        self.timeout.setRange(30, 600)
        self.timeout.setValue(180)
        self.timeout.setSuffix(" s")
        form.addRow("Give up after", self.timeout)
        return page

    def _sources_page(self, cache_count: int) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_note("Where hop locations come from, in the order they are tried. "
                               "Each line says what leaves this machine when it is on."))
        self.use_hoiho = QCheckBox("CAIDA Hoiho: router hostname rules")
        self.use_hoiho.setChecked(True)
        layout.addWidget(self.use_hoiho)
        layout.addWidget(_note("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Sends: public router hostnames "
                               "from the trace, to api.hoiho.caida.org."))
        site = QCheckBox("Carrier site-code table")
        site.setChecked(True)
        site.setEnabled(False)
        layout.addWidget(site)
        layout.addWidget(_note("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Offline, bundled. Sends nothing."))
        self.use_ipdb = QCheckBox("IP geolocation database (fallback)")
        self.use_ipdb.setChecked(True)
        layout.addWidget(self.use_ipdb)
        layout.addWidget(_note("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Sends: public hop addresses, to "
                               "RIPEstat (stat.ripe.net)."))
        self.use_ptr = QCheckBox("Reverse DNS for hops without a name")
        self.use_ptr.setChecked(True)
        layout.addWidget(self.use_ptr)
        layout.addWidget(_note("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Sends: PTR queries for public hop "
                               "addresses, to your own DNS resolver."))
        layout.addWidget(_rule())
        layout.addWidget(_note("Private, CGNAT and reserved addresses are never looked up "
                               "anywhere, whatever is switched on."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Keep Hoiho answers for"))
        self.ttl = QSpinBox()
        self.ttl.setRange(1, 365)
        self.ttl.setValue(30)
        self.ttl.setSuffix(" days")
        row.addWidget(self.ttl)
        row.addStretch(1)
        self.clear_cache = QPushButton(f"Clear cache ({cache_count} hostnames)")
        row.addWidget(self.clear_cache)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _atlas_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.atlas_on = QCheckBox("Offer “Trace from a RIPE Atlas probe” in the Trace menu")
        layout.addWidget(self.atlas_on)
        form = QFormLayout()
        self.atlas_key = QLineEdit()
        self.atlas_key.setEchoMode(QLineEdit.Password)
        self.atlas_key.setPlaceholderText("Your own RIPE Atlas API key")
        form.addRow("API key", self.atlas_key)
        layout.addLayout(form)
        layout.addWidget(_note(
            "Create a key at <a href='https://atlas.ripe.net/keys/'>atlas.ripe.net/keys</a> "
            "with only <i>schedule a new measurement</i> permission. The key is stored in "
            "your config folder and sent only to RIPE Atlas. Each traceroute costs 30 of "
            "your credits."))
        layout.addWidget(_rule())
        layout.addWidget(_note(
            "<b>Atlas measurements are public.</b> RIPE publishes every measurement, including "
            "the target, in its public database. You will be asked to confirm this before the "
            "first Atlas trace. Your origin coordinates are never sent: a probe is chosen by "
            "your network and country."))
        layout.addStretch(1)
        return page

    def _privacy_page(self, history_count: int) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.history_on = QCheckBox("Keep a history of the last 50 traces")
        self.history_on.setChecked(True)
        layout.addWidget(self.history_on)
        layout.addWidget(_note("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Stored as JSON in your config "
                               "folder on this machine. Turn it off and nothing is stored."))
        row = QHBoxLayout()
        self.clear_history = QPushButton(f"Clear history ({history_count} traces)")
        row.addWidget(self.clear_history)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(_rule())
        layout.addWidget(_note("No telemetry. No automatic update checks: Help › Check for "
                               "updates asks GitHub for the latest release tag, and only when "
                               "you choose it. Help › Privacy lists everything that leaves "
                               "this machine."))
        layout.addStretch(1)
        return page


# ------------------------------------------------------------------- export ---

class ExportDialog(QDialog):
    FORMATS = (
        ("png", "PNG image",
         "The whole route at 1600 × 900, with the legend and where the data came from."),
        ("pdf", "PDF report",
         "Title, target, date, origin, the map, the hop table, unplaced hops with reasons, "
         "the trace tool and flags, and the raw trace as an appendix."),
        ("json", "JSON route model",
         "Every hop, every candidate location and why it was used or rejected. Schema: "
         "route.schema.json."),
    )

    def __init__(self, parent=None, selected: str = "pdf"):
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.group = QButtonGroup(self)
        for key, title, body in self.FORMATS:
            box = QFrame()
            box.setFrameShape(QFrame.StyledPanel)
            grid = QGridLayout(box)
            grid.setContentsMargins(12, 10, 12, 10)
            radio = QRadioButton(title)
            font = radio.font()
            font.setBold(True)
            radio.setFont(font)
            radio.setProperty("format", key)
            self.group.addButton(radio)
            radio.setChecked(key == selected)
            grid.addWidget(radio, 0, 0, 1, 2)
            grid.addWidget(_note(body), 1, 0, 1, 2)
            if key == "pdf":
                self.appendix = QCheckBox("Include the raw trace text")
                self.appendix.setChecked(True)
                grid.addWidget(self.appendix, 2, 0)
            if key == "png":
                self.png_dark = QCheckBox("Dark map")
                grid.addWidget(self.png_dark, 2, 0)
            layout.addWidget(box)
        layout.addWidget(_note("Nothing is written anywhere except the file you choose."))
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.choose = buttons.addButton("Choose file…", QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected(self) -> str:
        button = self.group.checkedButton()
        return button.property("format") if button else "pdf"


# ------------------------------------------------------------------- Atlas ----

class AtlasWarningDialog(QDialog):
    """Must be acknowledged before the first Atlas trace."""

    def __init__(self, parent=None, target: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Trace from a RIPE Atlas probe")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        title = QLabel("<b style='font-size:15px'>This measurement will be public</b>")
        title.setTextFormat(Qt.RichText)
        layout.addWidget(title)
        body = QLabel(
            "RIPE Atlas publishes every measurement in its public database, including the "
            f"target you trace{(' (<b>' + target + '</b>)') if target else ''}, the probe that "
            "ran it, the time, and your Atlas account. It cannot be made private or deleted "
            "afterwards.<br><br>"
            "What is <b>not</b> sent: your origin coordinates. The probe is chosen by your "
            "network (AS number) and country.<br><br>"
            "The trace uses your own API key and costs 30 credits.")
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)
        layout.addWidget(body)
        self.ack = QCheckBox("I understand that this measurement and its target will be public.")
        layout.addWidget(self.ack)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.go = buttons.addButton("Trace with Atlas", QDialogButtonBox.AcceptRole)
        self.go.setEnabled(False)
        self.ack.toggled.connect(self.go.setEnabled)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


# -------------------------------------------------------------------- paste ---

class PasteTraceDialog(QDialog):
    def __init__(self, parent=None, text: str = "", detected: str = "", origin_label: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Paste a trace")
        self.resize(680, 460)
        layout = QVBoxLayout(self)
        layout.addWidget(_note("Output of <code>tracert</code>, <code>traceroute</code> or "
                               "<code>mtr --report</code> from any machine. It is analysed here; "
                               "nothing is uploaded except the lookups listed in Settings "
                               "› Sources."))
        self.edit = QPlainTextEdit(text)
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.edit.setFont(mono)
        self.edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.edit, 1)
        row = QHBoxLayout()
        self.detected = QLabel(detected)
        row.addWidget(self.detected)
        row.addStretch(1)
        row.addWidget(QLabel(f"Origin: {origin_label}"))
        change = QPushButton("Change…")
        row.addWidget(change)
        layout.addLayout(row)
        layout.addWidget(_note("The origin is where the trace was run from. For a trace run "
                               "on another machine, set that machine's city here."))
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.go = buttons.addButton("Analyse", QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


# ------------------------------------------------------------------ privacy ---

PRIVACY_HTML = """
<h3>What leaves this machine</h3>
<p>Nothing is sent anywhere until you run or open a trace, and then only this:</p>
<table cellpadding="5">
<tr><td><b>Router hostnames</b></td><td>to CAIDA Hoiho (api.hoiho.caida.org), to read the
location the carrier's naming scheme gives. Only public hostnames; never a local name.</td></tr>
<tr><td><b>Hop IP addresses</b></td><td>to RIPEstat (stat.ripe.net), the IP geolocation
fallback. Only public addresses.</td></tr>
<tr><td><b>PTR queries</b></td><td>to your own DNS resolver, for hops that came back without
a name.</td></tr>
<tr><td><b>One public IP lookup</b></td><td>to find your approximate city, and only while no
origin is set. Set one in Settings and it never happens.</td></tr>
<tr><td><b>RIPE Atlas</b></td><td>only if you enable it with your own key: the target, to
schedule a public measurement.</td></tr>
<tr><td><b>Update check</b></td><td>only when you choose Help &rsaquo; Check for updates: one
request to GitHub for the latest release tag.</td></tr>
</table>
<p>Private, CGNAT and reserved addresses are never looked up. There is no telemetry and no
automatic update check.</p>
<h3>What stays on this machine</h3>
<p>In your config folder: settings, the Hoiho answer cache (30 days, clearable) and, if it is
on, the history of the last 50 traces (clearable). Exports go only to the file you choose.</p>
"""


class PrivacyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Privacy")
        self.resize(600, 520)
        layout = QVBoxLayout(self)
        view = QTextBrowser()
        view.setHtml(PRIVACY_HTML)
        view.setOpenExternalLinks(True)
        layout.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
