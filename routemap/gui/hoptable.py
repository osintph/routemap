"""
The hop table: one row per hop, sortable, copyable as tab-separated text.
After a path discovery (0.4.0) a hop where the paths part ways has a sub-row
per responder, and a Paths column says which paths use each row.

The hostname column shows the hostname that produced the placement, which on an
ECMP hop is not necessarily the first one the hop answered from (FalconEye
v3.35.3). Every other address and name is in the row's tooltip.
"""
from __future__ import annotations

import html

from PySide6.QtCore import (QAbstractTableModel, QItemSelection, QItemSelectionModel, QModelIndex,
                            QSortFilterProxyModel, Qt, Signal)
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from routemap.gui import theme
from routemap.insight import RPKI_SHORT
from routemap_engine.geo import ANNOT_ICMP_LIMIT

# Ordered by what a reader needs first: where each hop is and how we know, then
# the evidence. At a 1440-pixel window the first seven are always visible.
COLUMNS = ["#", "Location", "Source", "ASN", "RPKI", "Hostname", "IP address", "RTT min", "RTT avg",
           "Loss", "Notes"]
KEYS = ["hop", "place", "source", "asn", "rpki", "hostname", "address", "min", "avg", "loss", "notes"]
WIDTHS = [32, 132, 150, 78, 64, 186, 112, 76, 76, 50]
NUMERIC = {"hop", "min", "avg", "loss"}
# Continuous mode: the mtr columns first, then where the hop is.
LIVE_COLUMNS = ["#", "Location", "Loss", "Sent", "Last", "Avg", "Best", "Worst", "StDev", "Source", "ASN",
                "Hostname", "IP address", "Notes"]
LIVE_KEYS = ["hop", "place", "loss", "sent", "last", "avg", "best", "worst", "stdev", "source", "asn",
             "hostname", "address", "notes"]
LIVE_WIDTHS = [32, 132, 70, 50, 62, 62, 62, 62, 58, 150, 78, 186, 112]
LIVE_NUMERIC = {"hop", "loss", "sent", "last", "avg", "best", "worst", "stdev"}
# A path discovery (0.4.0): which paths use each row. A hop where the paths
# part ways gets a sub-row per responder (9a, 9b, ...).
PATH_COLUMNS = ["#", "Paths", *COLUMNS[1:]]
PATH_KEYS = ["hop", "paths", *KEYS[1:]]
PATH_WIDTHS = [40, 70, *WIDTHS[1:]]
ALL_PATHS = "all"


def path_rows(hops: list[dict], paths: list[dict]) -> list[dict]:
    """The table's rows for a route with discovered *paths*: every hop, with
    the paths through it, and after a hop where the paths answered from more
    than one router, one sub-row per router (its own place, from the path's
    located hops)."""
    rows = []
    for hop in hops:
        ttl = hop.get("hop")
        by_addr: dict[str, list[str]] = {}
        located: dict[str, dict] = {}
        for p in paths:
            entry = next((h for h in p.get("located") or [] if h.get("hop") == ttl), None)
            if entry and entry.get("address"):
                by_addr.setdefault(entry["address"], []).append(p.get("id") or "?")
                located.setdefault(entry["address"], entry)
        ids_here = [i for ids in by_addr.values() for i in ids]
        main = dict(hop)
        main["_paths"] = ALL_PATHS if len(by_addr) <= 1 and len(ids_here) == len(paths) else " ".join(sorted(ids_here))
        rows.append(main)
        if len(by_addr) < 2:
            continue
        for n, (addr, ids) in enumerate(by_addr.items()):
            sub = {k: v for k, v in located[addr].items()}
            sub.update({"hop": ttl, "_sub": "abcdefghijklmnop"[n % 16], "_paths": " ".join(ids),
                        "addresses": [addr], "hostnames": [located[addr]["hostname"]] if located[addr].get("hostname")
                        else [], "annotations": [], "loss_pct": None})
            rows.append(sub)
    return rows
_LIVE_FIELDS = {"last": "last_ms", "best": "best_ms", "worst": "worst_ms", "stdev": "stdev_ms"}

# Short forms of the engine's annotation labels, for a narrow column. The full
# label and its detail are in the tooltip.
NOTE_SHORT = {
    "local / ISP internal": "local",
    "location impossible for RTT": "RTT rules out location",
    "likely asymmetric return path": "asymmetric return",
    "ICMP rate limiting, not real loss": "ICMP rate limiting",
    "destination or path does not answer ICMP": "no ICMP reply",
    "answered the final TTL 255 probe": "TTL 255 probe",
}


def rate_limited(hop: dict) -> bool:
    """Loss at this hop is the router rate-limiting its replies, not real loss."""
    return ANNOT_ICMP_LIMIT in (hop.get("annotations") or [])


def _dot(color: QColor, hollow: bool = False) -> QIcon:
    from PySide6.QtGui import QPen
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    if hollow:
        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(2, 2, 8, 8)
    else:
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(1, 1, 10, 10)
    painter.end()
    return QIcon(pixmap)


class HopModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hops: list[dict] = []
        self.source_hops: list[dict] = []    # the hops as given; .hops adds a path discovery's sub-rows
        self.paths_: list[dict] | None = None
        self.icons: dict = {}
        self.details: dict = {}       # str(hop) -> {"prefix", "rpki"} from the online insight
        self.marks: dict = {}         # hop -> diff mark
        self.columns, self.keys, self.numeric = COLUMNS, KEYS, NUMERIC

    def set_live(self, on: bool) -> None:
        """Switch between the trace columns and continuous mode's mtr columns."""
        self.beginResetModel()
        if on:
            self.columns, self.keys, self.numeric = LIVE_COLUMNS, LIVE_KEYS, LIVE_NUMERIC
        else:
            self.columns, self.keys, self.numeric = COLUMNS, KEYS, NUMERIC
        self.endResetModel()

    def set_hops(self, hops: list[dict], details: dict | None = None, marks: dict | None = None,
                 paths: list[dict] | None = None):
        self.beginResetModel()
        self.source_hops, self.paths_ = list(hops), paths
        if self.keys is not LIVE_KEYS:
            if paths and len(paths) > 1:
                self.columns, self.keys = PATH_COLUMNS, PATH_KEYS
                hops = path_rows(hops, paths)
            else:
                self.columns, self.keys = COLUMNS, KEYS
        self.hops = list(hops)
        self.details = dict(details or {})
        self.marks = dict(marks or {})
        palette = theme.current()
        self.icons = {k: _dot(v) for k, v in palette.sources.items()}
        self.icons["country"] = _dot(palette.sources["ip-db"], hollow=True)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.hops)

    def columnCount(self, parent=QModelIndex()):
        return len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columns[section]
        return None

    def text(self, hop: dict, column: int) -> str:
        key = self.keys[column]
        if key == "hop":
            return str(hop["hop"]) + hop.get("_sub", "")
        if key == "paths":
            return hop.get("_paths", "")
        if key == "sent":
            return "" if hop.get("sent") is None else str(hop["sent"])
        if key in _LIVE_FIELDS:
            value = hop.get(_LIVE_FIELDS[key])
            return "" if value is None else f"{value:.1f}"
        if key == "avg" and self.keys is LIVE_KEYS:
            value = hop.get("avg_ms")
            return "" if value is None else f"{value:.1f}"
        if key == "loss" and self.keys is LIVE_KEYS:
            loss = hop.get("loss_pct")
            return "" if loss is None else f"{loss:.1f}%"
        if key == "address":
            extra = len(hop.get("addresses") or []) - 1
            return (hop.get("address") or "*") + (f" (+{extra})" if extra > 0 else "")
        if key == "hostname":
            extra = len(hop.get("hostnames") or []) - 1
            return (hop.get("hostname") or "") + (f" (+{extra})" if extra > 0 else "")
        if key in ("min", "avg"):
            value = hop.get("min_rtt_ms" if key == "min" else "avg_rtt_ms")
            return "" if value is None else f"{value:.1f} ms"
        if key == "loss":
            loss = hop.get("loss_pct")
            return "" if loss is None else f"{loss:.0f}%"
        if key == "place":
            from routemap.gui.mapview import place_label
            return place_label(hop)
        if key == "source":
            from routemap.gui.mapview import source_label
            return source_label(hop)
        if key == "notes":
            notes = [NOTE_SHORT.get(a, a) for a in hop.get("annotations") or []]
            if hop.get("hop") in self.marks:
                notes.insert(0, theme.DIFF_LABELS.get(self.marks[hop["hop"]], ""))
            return ", ".join(n for n in notes if n)
        if key == "asn":
            return f"AS{hop['asn']}" if hop.get("asn") else ""
        if key == "rpki":
            state = (self.details.get(str(hop["hop"])) or {}).get("rpki")
            return RPKI_SHORT.get(state, "") if state else ""
        return ""

    def spoken(self, hop: dict) -> str:
        """The row as a screen reader says it: number, place, network, RTT, loss, notes."""
        parts = [f"Hop {hop['hop']}{hop.get('_sub', '')}"]
        if hop.get("_paths") and hop["_paths"] != ALL_PATHS:
            parts.append(f"paths {hop['_paths']}")
        for key in ("place", "asn", "address"):
            value = self.text(hop, self.keys.index(key)) if key in self.keys else ""
            if value:
                parts.append(value)
        rtt = hop.get("min_rtt_ms")
        if rtt is not None:
            parts.append(f"{rtt:.1f} milliseconds")
        loss = hop.get("loss_pct")
        if loss:
            parts.append(f"{loss:.0f} percent loss" + (", ICMP rate limiting, not real loss"
                                                        if rate_limited(hop) else ""))
        notes = [a for a in hop.get("annotations") or [] if a != ANNOT_ICMP_LIMIT]
        parts.extend(notes)
        return ", ".join(parts)

    def sort_key(self, hop: dict, column: int):
        key = self.keys[column]
        if key == "sent":
            return hop.get("sent") or 0
        if key in _LIVE_FIELDS:
            value = hop.get(_LIVE_FIELDS[key])
            return float("inf") if value is None else value
        if key == "hop":
            sub = hop.get("_sub")
            return hop["hop"] + ((ord(sub) - 96) / 100 if sub else 0)
        if key in ("min", "avg"):
            value = hop.get("min_rtt_ms" if key == "min" else "avg_rtt_ms")
            return float("inf") if value is None else value
        if key == "loss":
            loss = hop.get("loss_pct")
            return -1.0 if loss is None else loss
        return self.text(hop, column).lower()

    def tooltip(self, hop: dict) -> str:
        lines = [f"<b>Hop {html.escape(str(hop['hop']))}</b>"]
        if hop.get("addresses"):
            lines.append("Addresses: " + html.escape(", ".join(hop["addresses"])))
        if hop.get("hostnames"):
            lines.append("Hostnames: " + html.escape(", ".join(hop["hostnames"])))
        lines.append("Placed by: " + html.escape(theme.SOURCE_LABELS.get(hop.get("source"), "")))
        if hop.get("distance_km") is not None and hop.get("rtt_budget_km") is not None:
            lines.append(f"{hop['distance_km']:,.0f} km from origin; the fastest probe allows "
                         f"{hop['rtt_budget_km']:,.0f} km")
        if hop.get("match_strs"):
            lines.append("Hostname rule matched: " + html.escape(", ".join(hop["match_strs"])))
        if hop.get("carrier"):
            lines.append(f"Site code {html.escape(hop.get('site_code') or '')} in "
                         f"{html.escape(hop['carrier'])}'s published list")
        if hop.get("source") == "ip-db":
            lines.append("IP database: " + ("DB-IP Lite City, on this machine" if hop.get("ip_provider") == "dbip"
                                            else "RIPEstat, online"))
        if hop.get("asn"):
            lines.append(f"AS{html.escape(str(hop['asn']))} " + html.escape(str(hop.get("as_org") or "")))
        detail = self.details.get(str(hop["hop"])) or {}
        if detail.get("prefix"):
            lines.append(f"Routed prefix {html.escape(detail['prefix'])}, RPKI "
                         f"{html.escape(RPKI_SHORT.get(detail.get('rpki'), detail.get('rpki') or 'unavailable'))}")
        if hop.get("reason") and hop.get("lat") is None:
            lines.append("Not placed: " + html.escape(hop["reason"]))
        for note in hop.get("annotation_details") or []:
            lines.append(html.escape(note))
        return "<br>".join(lines)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        hop, column = self.hops[index.row()], index.column()
        if role == Qt.DisplayRole:
            return self.text(hop, column)
        if role == Qt.UserRole:
            return self.sort_key(hop, column)
        if role == Qt.DecorationRole and self.keys[column] == "source":
            if hop.get("precision") == "country":
                return self.icons.get("country")
            return self.icons.get(hop.get("source"))
        if role == Qt.ToolTipRole:
            return self.tooltip(hop)
        if role == Qt.AccessibleTextRole:
            return self.spoken(hop) if column == 0 else f"{self.columns[column]}: {self.text(hop, column) or 'none'}"
        if role == Qt.TextAlignmentRole and self.keys[column] in self.numeric:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and self.keys[column] == "rpki":
            state = (self.details.get(str(hop["hop"])) or {}).get("rpki") or ""
            if state.startswith("invalid"):
                return QColor("#c0392b")
        if role == Qt.ForegroundRole and self.keys[column] == "loss" and rate_limited(hop):
            return QColor(theme.current().overlay_muted)
        if role == Qt.ForegroundRole and hop.get("lat") is None:
            return QColor(theme.current().overlay_muted)
        if role == Qt.BackgroundRole and hop.get("hop") in self.marks:
            color = QColor(theme.diff_color(theme.current(), self.marks[hop["hop"]]))
            color.setAlpha(40)
            return color
        return None


class HopTable(QTableView):
    """Sortable, copyable; selection is reported as hop numbers so the map can follow."""

    hopsSelected = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model_ = HopModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model_)
        self.proxy.setSortRole(Qt.UserRole)
        self.setModel(self.proxy)
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.AscendingOrder)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideMiddle)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(24)
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        self._widths(WIDTHS)
        self._syncing = False
        self.selectionModel().selectionChanged.connect(self._selection_changed)

    def _widths(self, widths) -> None:
        for column, width in enumerate(widths):
            self.setColumnWidth(column, width)

    def set_live(self, on: bool) -> None:
        """The mtr columns for a continuous session, or the trace columns."""
        if (self.model_.keys is LIVE_KEYS) == on:
            return
        self.model_.set_live(on)
        self._widths(LIVE_WIDTHS if on else WIDTHS)

    def _selection_changed(self, *_):
        if self._syncing:
            return
        self.hopsSelected.emit(self.selected_hops())

    def selected_hops(self) -> list[int]:
        rows = sorted({i.row() for i in self.selectionModel().selectedRows()})
        out = []
        for row in rows:
            source = self.proxy.mapToSource(self.proxy.index(row, 0)).row()
            if 0 <= source < len(self.model_.hops):
                n = self.model_.hops[source]["hop"]
                if n not in out:
                    out.append(n)
        return out

    def select_hops(self, hops: list[int], scroll: bool = True):
        """Select the rows for *hops* without echoing the change back."""
        wanted = set(hops)
        selection = QItemSelection()
        first = None
        for row in range(self.proxy.rowCount()):
            source = self.proxy.mapToSource(self.proxy.index(row, 0)).row()
            if self.model_.hops[source]["hop"] in wanted:
                left = self.proxy.index(row, 0)
                right = self.proxy.index(row, self.proxy.columnCount() - 1)
                selection.select(left, right)
                first = left if first is None else first
        self._syncing = True
        try:
            self.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)
            if first is not None:
                self.selectionModel().setCurrentIndex(first, QItemSelectionModel.NoUpdate)
                if scroll:
                    self.scrollTo(first, QAbstractItemView.PositionAtCenter)
        finally:
            self._syncing = False

    def set_hops(self, hops: list[dict], details: dict | None = None, marks: dict | None = None,
                 paths: list[dict] | None = None):
        """Replace the rows, keeping the selection (by hop number) and scroll position."""
        keep = self.selected_hops()
        scroll = self.verticalScrollBar().value()
        self._syncing = True
        before = self.model_.keys
        try:
            self.model_.set_hops(hops, details, marks, paths)
            if self.model_.keys is not before:
                self._widths(PATH_WIDTHS if self.model_.keys is PATH_KEYS else WIDTHS)
            self.sortByColumn(self.horizontalHeader().sortIndicatorSection(),
                              self.horizontalHeader().sortIndicatorOrder())
        finally:
            self._syncing = False
        if keep:
            self.select_hops(keep, scroll=False)
        self.verticalScrollBar().setValue(scroll)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_selection()
            return
        super().keyPressEvent(event)

    @staticmethod
    def _cell(text: str) -> str:
        """A cell a spreadsheet takes as text: one that would start a formula
        (= + - @, or a tab or CR before one) gets a leading apostrophe. Numbers,
        negative ones included, and the "-" for no value stay as they are."""
        if text[:1] in ("=", "+", "-", "@", "\t", "\r") and text != "-":
            try:
                float(text)
            except ValueError:
                return "'" + text.replace("\t", " ").replace("\r", " ")
        return text

    def copy_selection(self) -> str:
        """Selected rows (or all of them) as tab-separated text with a header."""
        rows = sorted({i.row() for i in self.selectionModel().selectedIndexes()}) \
            or list(range(self.proxy.rowCount()))
        lines = ["\t".join(self.model_.columns)]
        for row in rows:
            source_row = self.proxy.mapToSource(self.proxy.index(row, 0)).row()
            hop = self.model_.hops[source_row]
            lines.append("\t".join(self._cell(self.model_.text(hop, c)) for c in range(len(self.model_.columns))))
        text = "\n".join(lines) + "\n"
        QGuiApplication.clipboard().setText(text)
        return text
