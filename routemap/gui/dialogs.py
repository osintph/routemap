"""Dialogs: settings, export, the RIPE Atlas warning, paste a trace, privacy."""
from __future__ import annotations

import shlex

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QFrame, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QPlainTextEdit,
                               QPushButton, QRadioButton, QSpinBox, QTabWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from routemap.__about__ import (CONTACT_EMAIL, DISPLAY_NAME, DONATE_ADDRESSES, DONATE_LINKS,
                                DONATE_URL, DONATIONS_PAY_FOR, SITE_LINKED)
from routemap.config import ORIGIN_AUTO, ORIGIN_CITY, ORIGIN_COORDS, ORIGIN_MAP, Settings
from routemap_engine.runner import DEFAULT_FLAGS


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
    """Every setting, read from and written back to a config.Settings."""

    pickRequested = Signal()
    clearCacheRequested = Signal()
    clearHistoryRequested = Signal()
    updateDataRequested = Signal()
    importDataRequested = Signal()

    def __init__(self, parent=None, settings: Settings | None = None, *, origin_label: str = "",
                 tools: dict | None = None, cache_count: int = 0, history_count: int = 0):
        super().__init__(parent)
        self.settings = settings or Settings()
        self.setWindowTitle(f"{DISPLAY_NAME} Settings")
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._origin_page(origin_label), "Origin")
        self.tabs.addTab(self._trace_page(tools or {}), "Trace")
        self.tabs.addTab(self._sources_page(cache_count), "Sources")
        self.tabs.addTab(self._map_page(), "Map")
        self.tabs.addTab(self._atlas_page(), "RIPE Atlas")
        self.tabs.addTab(self._privacy_page(history_count), "Privacy")
        layout.addWidget(self.tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---- origin
    def _origin_page(self, origin_label: str) -> QWidget:
        s = self.settings
        page = QWidget()
        layout = QVBoxLayout(page)
        self.current = QLabel()
        self.current.setTextFormat(Qt.RichText)
        self.set_current_origin(origin_label)
        layout.addWidget(self.current)
        layout.addWidget(_note("Every route starts here. It is your machine's location, "
                               "never a server's."))
        layout.addWidget(_rule())

        self.origin_group = QButtonGroup(page)
        self.origin_auto = QRadioButton("From my public IP address")
        self.origin_city = QRadioButton("A city")
        self.origin_coords = QRadioButton("Coordinates")
        self.origin_map = QRadioButton("Picked on the map")
        self.modes = {ORIGIN_AUTO: self.origin_auto, ORIGIN_CITY: self.origin_city,
                      ORIGIN_COORDS: self.origin_coords, ORIGIN_MAP: self.origin_map}
        for i, button in enumerate(self.modes.values()):
            self.origin_group.addButton(button, i)
        self.modes.get(s.origin_mode, self.origin_auto).setChecked(True)

        layout.addWidget(self.origin_auto)
        layout.addWidget(_note("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;One lookup of your public IP, "
                               "city level. Approximate; wrong on a VPN or exit node."))
        layout.addWidget(self.origin_city)
        city_row = QHBoxLayout()
        city_row.setContentsMargins(24, 0, 0, 0)
        self.city_search = QLineEdit()
        self.city_search.setPlaceholderText("Search the bundled city list (offline)")
        city_row.addWidget(self.city_search)
        layout.addLayout(city_row)
        self.city_results = QListWidget()
        self.city_results.setMaximumHeight(110)
        results_row = QHBoxLayout()
        results_row.setContentsMargins(24, 0, 0, 0)
        results_row.addWidget(self.city_results)
        layout.addLayout(results_row)
        self.city_search.textChanged.connect(self._search_cities)
        self.city_search.textEdited.connect(lambda *_: self.origin_city.setChecked(True))
        self.city_results.itemClicked.connect(lambda *_: self.origin_city.setChecked(True))
        if s.origin_mode == ORIGIN_CITY and s.origin_label:
            self.city_search.setText(s.origin_label.split(",")[0])
            for row in range(self.city_results.count()):
                if self.city_results.item(row).text() == s.origin_label:
                    self.city_results.setCurrentRow(row)
                    break

        layout.addWidget(self.origin_coords)
        coords = QHBoxLayout()
        coords.setContentsMargins(24, 0, 0, 0)
        self.lat = QDoubleSpinBox()
        self.lat.setRange(-90, 90)
        self.lat.setDecimals(2)
        self.lon = QDoubleSpinBox()
        self.lon.setRange(-180, 180)
        self.lon.setDecimals(2)
        if s.origin_lat is not None:
            self.lat.setValue(s.origin_lat)
            self.lon.setValue(s.origin_lon)
        for spin in (self.lat, self.lon):
            spin.valueChanged.connect(lambda *_: self.origin_coords.setChecked(True)
                                      if not self.origin_map.isChecked() else None)
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
        self.pick_button.clicked.connect(self.pickRequested)
        pick.addWidget(self.pick_button)
        pick.addStretch(1)
        layout.addLayout(pick)
        layout.addWidget(_rule())
        layout.addWidget(_note("A chosen origin is remembered, and while one is set the public "
                               "IP lookup is skipped entirely. City list: GeoNames, CC BY 4.0."))
        layout.addStretch(1)
        return page

    def set_current_origin(self, label: str):
        self.current.setText(f"<b>Current origin:</b> {label or 'not set yet'}")

    def set_picked(self, lat: float, lon: float):
        self.lat.blockSignals(True)
        self.lon.blockSignals(True)
        self.lat.setValue(lat)
        self.lon.setValue(lon)
        self.lat.blockSignals(False)
        self.lon.blockSignals(False)
        self.origin_map.setChecked(True)

    def _search_cities(self, text: str):
        from routemap_engine import cities

        self.city_results.clear()
        self._city_rows = cities.search(text)
        for row in self._city_rows:
            self.city_results.addItem(row["display"])
        if self._city_rows:
            self.city_results.setCurrentRow(0)

    # ---- trace
    def _trace_page(self, tools: dict) -> QWidget:
        s = self.settings
        page = QWidget()
        form = QFormLayout(page)
        self.tool = QComboBox()
        self.tool.addItem("Automatic", "auto")
        for name in ("traceroute", "mtr", "tracert"):
            status = "installed" if name in tools else "not available here"
            self.tool.addItem(f"{name} ({status})", name)
            if name not in tools:
                self.tool.model().item(self.tool.count() - 1).setEnabled(False)
        index = self.tool.findData(s.tool)
        self.tool.setCurrentIndex(max(0, index))
        form.addRow("Tool", self.tool)
        form.addRow("", _note("Detected at startup. tracert on Windows; traceroute on macOS "
                              "and Linux; mtr where installed (on macOS mtr needs administrator "
                              "rights, so it is not offered there)."))
        self.flags = {}
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        for name in ("traceroute", "mtr", "tracert"):
            edit = QLineEdit(shlex.join(s.flags_for(name)))
            edit.setFont(mono)
            edit.textChanged.connect(self._check_flags)
            self.flags[name] = edit
            form.addRow(f"{name} flags", edit)
        reset = QPushButton("Restore defaults")
        reset.clicked.connect(lambda: [self.flags[n].setText(shlex.join(DEFAULT_FLAGS[n]))
                                       for n in self.flags])
        form.addRow("", reset)
        self.flag_warning = _note("")
        form.addRow("", self.flag_warning)
        self.timeout = QSpinBox()
        self.timeout.setRange(30, 600)
        self.timeout.setValue(int(s.timeout_seconds))
        self.timeout.setSuffix(" s")
        form.addRow("Give up after", self.timeout)
        self._check_flags()
        return page

    def _check_flags(self, *_):
        from routemap_engine.runner import privileged_flags_in

        notes = []
        for name, edit in self.flags.items():
            try:
                flags = shlex.split(edit.text())
            except ValueError:
                notes.append(f"<b>{name}</b>: unbalanced quotes")
                continue
            needs = privileged_flags_in(name, flags)
            if needs:
                notes.append(f"<b>{name}</b>: {', '.join(needs)} needs administrator rights; "
                             "the trace will not ask for them and may fail")
        base = ("Probe types that need administrator rights (traceroute <code>-I</code> ICMP, "
                "<code>-T</code> TCP) are flagged, not escalated: the trace never runs with "
                "elevated privileges.")
        self.flag_warning.setText("<br>".join(notes) if notes else base)

    # ---- sources
    def _sources_page(self, cache_count: int) -> QWidget:
        s = self.settings
        page = QWidget()
        layout = QVBoxLayout(page)
        self.online = QCheckBox("Online lookups")
        font = self.online.font()
        font.setBold(True)
        self.online.setFont(font)
        self.online.setChecked(s.online_lookups)
        layout.addWidget(self.online)
        layout.addWidget(_note("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;On: CAIDA Hoiho, RIPEstat (IP database, "
                               "RPKI, BGP, abuse contacts), RIPE Atlas baselines, reverse DNS, each as "
                               "ticked below. Off: nothing new leaves this machine; placement uses the "
                               "offline data only (site codes, DB-IP Lite City and ASN)."))
        layout.addWidget(_rule())
        layout.addWidget(_note("Where hop locations come from, in the order they are tried. "
                               "Each line says what leaves this machine when it is on."))
        from routemap import policy
        self.use_hoiho = QCheckBox("CAIDA Hoiho: router hostname rules")
        self.use_hoiho.setChecked(s.use_hoiho and policy.HOIHO_ALLOWED)
        self.use_hoiho.setEnabled(policy.HOIHO_ALLOWED)
        layout.addWidget(self.use_hoiho)
        layout.addWidget(_note("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Sends: public router hostnames "
                               "from the trace, to api.hoiho.caida.org."))
        site = QCheckBox("Carrier site-code table")
        site.setChecked(True)
        site.setEnabled(False)
        layout.addWidget(site)
        layout.addWidget(_note("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Offline, bundled. Sends nothing."))
        from routemap import policy
        self.use_ipdb = QCheckBox("IP geolocation database (fallback)")
        self.use_ipdb.setChecked(s.use_ip_db and policy.RIPESTAT_ALLOWED)
        self.use_ipdb.setEnabled(policy.RIPESTAT_ALLOWED)
        if not policy.RIPESTAT_ALLOWED:
            self.use_ipdb.setToolTip(policy.RIPESTAT_OFF_NOTE)
        layout.addWidget(self.use_ipdb)
        layout.addWidget(_note("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Sends: public hop addresses, to "
                               "RIPEstat (stat.ripe.net)."))
        self.use_ptr = QCheckBox("Reverse DNS for hops without a name")
        self.use_ptr.setChecked(s.use_ptr)
        layout.addWidget(self.use_ptr)
        layout.addWidget(_note("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Sends: PTR queries for public hop "
                               "addresses, to your own DNS resolver."))
        layout.addWidget(_rule())
        layout.addWidget(_note("Private, CGNAT and reserved addresses are never looked up "
                               "anywhere, whatever is switched on."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Keep Hoiho and IP database answers for"))
        self.ttl = QSpinBox()
        self.ttl.setRange(1, 365)
        self.ttl.setValue(int(s.cache_ttl_days))
        self.ttl.setSuffix(" days")
        row.addWidget(self.ttl)
        row.addStretch(1)
        self.clear_cache = QPushButton(f"Clear cache ({cache_count} answers)")
        self.clear_cache.setEnabled(cache_count > 0)
        self.clear_cache.clicked.connect(self.clearCacheRequested)
        row.addWidget(self.clear_cache)
        layout.addLayout(row)
        layout.addWidget(_rule())
        data = QHBoxLayout()
        self.data_label = QLabel()
        self.data_label.setWordWrap(True)
        self.data_label.setTextFormat(Qt.RichText)
        data.addWidget(self.data_label, 1)
        self.update_data = QPushButton("Update now")
        self.update_data.setToolTip("Downloads this month's DB-IP Lite City (about 60 MB) and ASN "
                                    "from download.db-ip.com.")
        self.update_data.clicked.connect(self.updateDataRequested)
        self.import_data = QPushButton("Import database file…")
        self.import_data.setToolTip("For a machine with no internet: a dbip-city-lite .mmdb or "
                                    ".mmdb.gz copied from elsewhere.")
        self.import_data.clicked.connect(self.importDataRequested)
        data.addWidget(self.update_data)
        data.addWidget(self.import_data)
        layout.addLayout(data)
        layout.addWidget(_note("DB-IP Lite, CC BY 4.0: IP Geolocation by "
                               "<a href='https://db-ip.com'>DB-IP</a>. Updated monthly; "
                               "<code>routemap data update</code> does the same from a terminal."))
        self.refresh_databases()
        self.online.toggled.connect(self._online_toggled)
        self._online_toggled(self.online.isChecked())
        layout.addStretch(1)
        return page

    def _online_toggled(self, on: bool):
        from routemap import policy
        self.use_hoiho.setEnabled(on and policy.HOIHO_ALLOWED)
        self.use_ipdb.setEnabled(on and policy.RIPESTAT_ALLOWED)
        self.use_ptr.setEnabled(on)

    def refresh_databases(self):
        from routemap import dbip
        city, asn = dbip.city_database(), dbip.asn_database()
        city_text = (f"City {city.month}" if city else
                     "City <b>not installed</b>: IP database placements come from RIPEstat, online")
        asn_text = f"ASN {asn.month}" + (" (bundled)" if asn and asn.bundled else "") if asn else "ASN missing"
        stale = " <span style='color:#b7791f'>(a newer month is out)</span>" if city and dbip.is_stale(city) else ""
        self.data_label.setText(f"<b>Offline data</b>: DB-IP Lite {city_text}; {asn_text}{stale}")

    # ---- map
    def _map_page(self) -> QWidget:
        s = self.settings
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.projection = QComboBox()
        self.projection.addItem("Flat (overview)", "flat")
        self.projection.addItem("Globe, centred on the route", "globe")
        self.projection.setCurrentIndex(1 if s.projection == "globe" else 0)
        form.addRow("Projection", self.projection)
        steps = QHBoxLayout()
        self.rtt_quiet = QDoubleSpinBox()
        self.rtt_quiet.setRange(0, 500)
        self.rtt_quiet.setDecimals(0)
        self.rtt_quiet.setSuffix(" ms")
        self.rtt_quiet.setValue(s.rtt_quiet_ms)
        self.rtt_hot = QDoubleSpinBox()
        self.rtt_hot.setRange(1, 1000)
        self.rtt_hot.setDecimals(0)
        self.rtt_hot.setSuffix(" ms")
        self.rtt_hot.setValue(s.rtt_hot_ms)
        steps.addWidget(QLabel("grey under"))
        steps.addWidget(self.rtt_quiet)
        steps.addWidget(QLabel("fully warm from"))
        steps.addWidget(self.rtt_hot)
        steps.addStretch(1)
        form.addRow("RTT step colours", steps)
        self.sensitive = QLineEdit(", ".join(s.sensitive_countries))
        self.sensitive.setPlaceholderText("Two-letter country codes, e.g. SG, CN")
        form.addRow("Sensitive countries", self.sensitive)
        self.falconeye = QLineEdit(s.falconeye_url)
        form.addRow("FalconEye", self.falconeye)
        layout.addLayout(form)
        layout.addWidget(_note("Sensitive countries are flagged in the route summary when a placed "
                               "hop is in one of them. FalconEye: right-click a hop, Open in "
                               "FalconEye opens IP Reputation there with the address on the clipboard."))
        layout.addWidget(_rule())
        layout.addWidget(_note("<b>Submarine cables: not available.</b> TeleGeography's cable data "
                               "is sold under licence; the overlay waits for a source the app may ship."))
        layout.addWidget(_note("<b>Exchange points: not available.</b> PeeringDB's terms do not allow "
                               "bundling its prefix list; possible later with their permission."))
        layout.addStretch(1)
        return page

    # ---- atlas
    def _atlas_page(self) -> QWidget:
        s = self.settings
        page = QWidget()
        layout = QVBoxLayout(page)
        self.atlas_on = QCheckBox("Offer “Trace from a RIPE Atlas probe” in the Trace menu")
        self.atlas_on.setChecked(s.atlas_enabled)
        layout.addWidget(self.atlas_on)
        form = QFormLayout()
        self.atlas_key = QLineEdit(s.atlas_key)
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

    # ---- privacy
    def _privacy_page(self, history_count: int) -> QWidget:
        s = self.settings
        page = QWidget()
        layout = QVBoxLayout(page)
        self.history_on = QCheckBox("Keep a history of the last 50 traces")
        self.history_on.setChecked(s.history_enabled)
        layout.addWidget(self.history_on)
        layout.addWidget(_note("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Stored as JSON in your config "
                               "folder on this machine. Turn it off and nothing is stored."))
        row = QHBoxLayout()
        self.clear_history = QPushButton(f"Clear history ({history_count} traces)")
        self.clear_history.setEnabled(history_count > 0)
        self.clear_history.clicked.connect(self.clearHistoryRequested)
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

    # ---- read back
    def values_into(self, settings: Settings) -> list[str]:
        """Copy the dialog into *settings*. Returns problems that stopped a field."""
        problems = []
        mode = next((m for m, b in self.modes.items() if b.isChecked()), ORIGIN_AUTO)
        if mode == ORIGIN_CITY:
            row = self.city_results.currentRow()
            rows = getattr(self, "_city_rows", [])
            if 0 <= row < len(rows):
                city = rows[row]
                settings.origin_mode = ORIGIN_CITY
                settings.origin_lat, settings.origin_lon = city["lat"], city["lon"]
                settings.origin_label = city["display"]
            elif settings.origin_mode != ORIGIN_CITY:
                problems.append("Choose a city from the list, or pick another kind of origin.")
        elif mode in (ORIGIN_COORDS, ORIGIN_MAP):
            from routemap_engine import cities

            lat, lon = round(self.lat.value(), 2), round(self.lon.value(), 2)
            near = cities.nearest(lat, lon)
            settings.origin_mode = mode
            settings.origin_lat, settings.origin_lon = lat, lon
            settings.origin_label = (near or {}).get("display") or f"{lat}, {lon}"
        else:
            settings.origin_mode = ORIGIN_AUTO
            settings.origin_lat = settings.origin_lon = settings.origin_label = None

        settings.tool = self.tool.currentData() or "auto"
        for name, edit in self.flags.items():
            try:
                settings.flags[name] = shlex.split(edit.text())
            except ValueError:
                problems.append(f"The {name} flags have unbalanced quotes; they were not changed.")
        settings.timeout_seconds = self.timeout.value()
        settings.online_lookups = self.online.isChecked()
        settings.projection = self.projection.currentData() or "flat"
        settings.rtt_quiet_ms = float(self.rtt_quiet.value())
        settings.rtt_hot_ms = float(self.rtt_hot.value())
        if settings.rtt_hot_ms <= settings.rtt_quiet_ms:
            problems.append("The fully warm RTT step must be above the grey one; it was set 1 ms above.")
        codes = [c.strip().upper() for c in self.sensitive.text().replace(";", ",").split(",") if c.strip()]
        bad = [c for c in codes if len(c) != 2 or not c.isalpha()]
        if bad:
            problems.append("Not two-letter country codes, so left out: " + ", ".join(bad))
        settings.sensitive_countries = [c for c in codes if c not in bad]
        url = self.falconeye.text().strip()
        if url and not url.startswith(("https://", "http://")):
            problems.append("The FalconEye address must start with https://; it was not changed.")
        else:
            settings.falconeye_url = url or "https://falconeye.osintph.info"
        from routemap import config as _config
        _config.normalise(settings)
        settings.use_hoiho = self.use_hoiho.isChecked()
        settings.use_ip_db = self.use_ipdb.isChecked()
        settings.use_ptr = self.use_ptr.isChecked()
        settings.cache_ttl_days = self.ttl.value()
        settings.atlas_enabled = self.atlas_on.isChecked()
        settings.atlas_key = self.atlas_key.text().strip()
        settings.history_enabled = self.history_on.isChecked()
        return problems


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
    changeOrigin = Signal()

    def __init__(self, parent=None, text: str = "", detected: str = "", origin_label: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Paste a trace")
        self.resize(680, 460)
        layout = QVBoxLayout(self)
        layout.addWidget(_note("Output of <code>tracert</code>, <code>traceroute</code> or "
                               "<code>mtr --report</code> from any machine. It is analysed here; "
                               "nothing is uploaded except the lookups listed in Settings "
                               "\u203a Sources."))
        self.edit = QPlainTextEdit()
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.edit.setFont(mono)
        self.edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.edit.setPlaceholderText("Paste the whole output here, header line included if you have it.")
        layout.addWidget(self.edit, 1)
        row = QHBoxLayout()
        self.detected = QLabel(detected)
        row.addWidget(self.detected)
        row.addStretch(1)
        self.origin = QLabel()
        row.addWidget(self.origin)
        change = QPushButton("Change\u2026")
        change.clicked.connect(self.changeOrigin)
        row.addWidget(change)
        layout.addLayout(row)
        layout.addWidget(_note("The origin is where the trace was run from. For a trace run "
                               "on another machine, set that machine's city here."))
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.go = buttons.addButton("Analyse", QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.set_origin_label(origin_label)
        self.edit.textChanged.connect(self._detect)
        self.edit.setPlainText(text)
        self._detect()

    def set_origin_label(self, label: str):
        self.origin.setText(f"Origin: {label or 'not set'}")

    def text(self) -> str:
        return self.edit.toPlainText()

    def _detect(self):
        from routemap_engine.parse import PARSER_LABELS, TraceParseError, parse_trace

        text = self.edit.toPlainText()
        if not text.strip():
            self.detected.setText("")
            self.go.setEnabled(False)
            return
        try:
            parsed = parse_trace(text)
        except TraceParseError as exc:
            self.detected.setText(f"<span style='color:#c0392b'>{exc}</span>")
            self.go.setEnabled(False)
            return
        self.detected.setText(f"Detected: {PARSER_LABELS[parsed.parser]}, {len(parsed.hops)} hops")
        self.go.setEnabled(True)


# ------------------------------------------------------------------ privacy ---

PRIVACY_HTML = """
<h3>What leaves this machine</h3>
<p>Nothing is sent anywhere until you run or open a trace, and then only this:</p>
<table cellpadding="5">
<tr><td><b>Router hostnames</b></td><td>to CAIDA Hoiho (api.hoiho.caida.org), to read the
location the carrier's naming scheme gives. Only public hostnames; never a local name.</td></tr>
<tr><td><b>Hop IP addresses</b></td><td>to RIPEstat (stat.ripe.net), the IP geolocation
fallback, for the addresses the offline DB-IP Lite City file does not place (all of them
while it is not installed). Only public addresses.</td></tr>
<tr><td><b>Route details</b></td><td>to RIPEstat: public hop addresses, their prefixes and
AS numbers, for RPKI, RIS paths and visibility, BGP updates and AS overviews; a hop's RIR
and abuse contact only when you open its details. To RIPE Atlas: two country codes and an
anchor's public name, for a typical latency (public data, no key).</td></tr>
<tr><td><b>Offline data</b></td><td>to download.db-ip.com, only when you choose Download or
Update now: one request per DB-IP Lite file.</td></tr>
<tr><td><b>PTR queries</b></td><td>to your own DNS resolver, for hops that came back without
a name.</td></tr>
<tr><td><b>One public IP lookup</b></td><td>to find your approximate city, and only while no
origin is set. Set one in Settings and it never happens.</td></tr>
<tr><td><b>RIPE Atlas</b></td><td>only if you enable it with your own key and choose Trace
from a RIPE Atlas probe. To atlas.ripe.net: your API key, your network's AS number (or, if
no probe is on it, your country code) to find a probe, and the target, to schedule the
measurement. To find the AS number, your public IP goes to RIPEstat once. Atlas
measurements, target included, are published by RIPE NCC. Your origin coordinates are
never sent: they only rank probes on this machine.</td></tr>
<tr><td><b>Update check</b></td><td>only when you choose Help &rsaquo; Check for updates: one
request to GitHub for the latest release tag.</td></tr>
</table>
<p><b>Settings &rsaquo; Sources &rsaquo; Online lookups</b> turns all of the above off at once
except Atlas traces you start, the update check and downloads you choose: hops are then
placed from offline data only.</p>
<p>Private, CGNAT and reserved addresses are never looked up. There is no telemetry and no
automatic update check.</p>
<p>Questions about privacy: <a href="mailto:support@getroutemap.app">support@getroutemap.app</a>.</p>
<h3>What stays on this machine</h3>
<p>In your config folder: settings, the Hoiho, IP database and RIPE detail answer caches
(clearable), the DB-IP Lite files and, if it is on, the history of the last 50 traces
(clearable). Exports go only to the file you choose.</p>
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


class NoticesDialog(QDialog):
    """THIRD_PARTY_NOTICES.md and the licence texts that ship with the build."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from routemap.gui.legal import notices_markdown
        self.setWindowTitle("Third-Party Notices")
        self.resize(720, 600)
        layout = QVBoxLayout(self)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setMarkdown(notices_markdown())
        layout.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class SupportDialog(QDialog):
    """Help > Support. Opened only from the menu, never on its own."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtGui import QGuiApplication
        self.setWindowTitle(f"Support {DISPLAY_NAME}")
        layout = QVBoxLayout(self)
        layout.addWidget(_note(
            f"{DISPLAY_NAME} is free and open source. If it is useful to you, donations pay for "
            f"{DONATIONS_PAY_FOR}."))
        links = " &nbsp;\u00b7&nbsp; ".join(f"<a href='{url}'>{name}</a>" for name, url in DONATE_LINKS)
        note = _note(links)
        note.setOpenExternalLinks(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.address_fields = {}
        for name, address in DONATE_ADDRESSES:
            row = QHBoxLayout()
            field = QLineEdit(address)
            field.setReadOnly(True)
            field.setMinimumWidth(420)
            field.setCursorPosition(0)
            copy = QPushButton("Copy")
            copy.clicked.connect(lambda _=False, a=address: QGuiApplication.clipboard().setText(a))
            row.addWidget(field, 1)
            row.addWidget(copy)
            form.addRow(name, row)
            self.address_fields[name] = field
        layout.addLayout(form)
        where = (f"QR codes and a GPG-signed list of these addresses: "
                 f"<a href='{DONATE_URL}'>{DONATE_URL}</a>. " if SITE_LINKED else "")
        more = _note(where + "Bug reports and good trace examples help too: "
                     f"<a href='mailto:{CONTACT_EMAIL}'>{CONTACT_EMAIL}</a>.")
        more.setOpenExternalLinks(True)
        layout.addWidget(more)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)



class CityDatabaseDialog(QDialog):
    """First run: offer DB-IP Lite City. Asked once; "Not now" is remembered."""

    DOWNLOAD, IMPORT, NOT_NOW = 2, 3, 0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Offline IP database")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Download DB-IP Lite City for offline placement?</b>"))
        layout.addWidget(_note(
            f"When a hop's hostname says nothing about where it is, {DISPLAY_NAME} falls back to an IP "
            "geolocation database. With DB-IP Lite City on this machine that lookup stays here; "
            "without it, the hop addresses are sent to RIPEstat. The file is about 60 MB to "
            "download (127 MB on disk), from download.db-ip.com, and is updated monthly. "
            "Licence CC BY 4.0, IP Geolocation by <a href='https://db-ip.com'>DB-IP</a>."))
        layout.addWidget(_note("No internet on this machine? Import a file copied from elsewhere. "
                               "You can do either later in Settings › Sources."))
        buttons = QDialogButtonBox()
        download = buttons.addButton("Download", QDialogButtonBox.AcceptRole)
        importer = buttons.addButton("Import File…", QDialogButtonBox.ActionRole)
        later = buttons.addButton("Not Now", QDialogButtonBox.RejectRole)
        download.setDefault(True)
        download.clicked.connect(lambda: self.done(self.DOWNLOAD))
        importer.clicked.connect(lambda: self.done(self.IMPORT))
        later.clicked.connect(lambda: self.done(self.NOT_NOW))
        layout.addWidget(buttons)


class DownloadDialog(QDialog):
    """Progress for the DB-IP downloads; Cancel stops them cleanly."""

    def __init__(self, parent=None):
        from PySide6.QtWidgets import QProgressBar
        super().__init__(parent)
        self.setWindowTitle("Updating offline data")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        self.label = QLabel("Starting…")
        layout.addWidget(self.label)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        layout.addWidget(self.bar)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.kind = ""

    def set_kind(self, kind: str):
        self.kind = kind
        self.label.setText(f"Downloading DB-IP Lite {'City' if kind == 'city' else 'ASN'}…")
        self.bar.setRange(0, 0)

    def set_progress(self, done: int, total: int):
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(1000 * done / total))
            self.label.setText(f"Downloading DB-IP Lite {'City' if self.kind == 'city' else 'ASN'}: "
                               f"{done / 1e6:.1f} of {total / 1e6:.1f} MB")
