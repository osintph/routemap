"""
The hop table: one row per hop, sortable, copyable as tab-separated text.

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

# Ordered by what a reader needs first: where each hop is and how we know, then
# the evidence. At a 1440-pixel window the first seven are always visible.
COLUMNS = ["#", "Location", "Source", "ASN", "RPKI", "Hostname", "IP address", "RTT min", "RTT avg",
           "Loss", "Notes"]
KEYS = ["hop", "place", "source", "asn", "rpki", "hostname", "address", "min", "avg", "loss", "notes"]
WIDTHS = [32, 132, 150, 78, 64, 186, 112, 76, 76, 50]
RPKI_SHORT = {"valid": "valid", "unknown": "no ROA", "invalid": "INVALID", "invalid_asn": "INVALID",
              "invalid_length": "INVALID"}
NUMERIC = {"hop", "min", "avg", "loss"}

# Short forms of the engine's annotation labels, for a narrow column. The full
# label and its detail are in the tooltip.
NOTE_SHORT = {
    "local / ISP internal": "local",
    "location impossible for RTT": "RTT rules out location",
    "likely asymmetric return path": "asymmetric return",
    "ICMP rate limiting, not real loss": "ICMP rate limiting",
    "destination or path does not answer ICMP": "no ICMP reply",
}


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
        self.icons: dict = {}
        self.details: dict = {}       # str(hop) -> {"prefix", "rpki"} from the online insight
        self.marks: dict = {}         # hop -> diff mark

    def set_hops(self, hops: list[dict], details: dict | None = None, marks: dict | None = None):
        self.beginResetModel()
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
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        return None

    def text(self, hop: dict, column: int) -> str:
        key = KEYS[column]
        if key == "hop":
            return str(hop["hop"])
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

    def sort_key(self, hop: dict, column: int):
        key = KEYS[column]
        if key == "hop":
            return hop["hop"]
        if key in ("min", "avg"):
            value = hop.get("min_rtt_ms" if key == "min" else "avg_rtt_ms")
            return float("inf") if value is None else value
        if key == "loss":
            loss = hop.get("loss_pct")
            return -1.0 if loss is None else loss
        return self.text(hop, column).lower()

    def tooltip(self, hop: dict) -> str:
        lines = [f"<b>Hop {hop['hop']}</b>"]
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
            lines.append(f"AS{hop['asn']} " + html.escape(hop.get("as_org") or ""))
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
        if role == Qt.DecorationRole and KEYS[column] == "source":
            if hop.get("precision") == "country":
                return self.icons.get("country")
            return self.icons.get(hop.get("source"))
        if role == Qt.ToolTipRole:
            return self.tooltip(hop)
        if role == Qt.TextAlignmentRole and KEYS[column] in NUMERIC:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and KEYS[column] == "rpki":
            state = (self.details.get(str(hop["hop"])) or {}).get("rpki") or ""
            if state.startswith("invalid"):
                return QColor("#c0392b")
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
        for column, width in enumerate(WIDTHS):
            self.setColumnWidth(column, width)
        self._syncing = False
        self.selectionModel().selectionChanged.connect(self._selection_changed)

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
                out.append(self.model_.hops[source]["hop"])
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

    def set_hops(self, hops: list[dict], details: dict | None = None, marks: dict | None = None):
        """Replace the rows, keeping the selection (by hop number) and scroll position."""
        keep = self.selected_hops()
        scroll = self.verticalScrollBar().value()
        self._syncing = True
        try:
            self.model_.set_hops(hops, details, marks)
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

    def copy_selection(self) -> str:
        """Selected rows (or all of them) as tab-separated text with a header."""
        rows = sorted({i.row() for i in self.selectionModel().selectedIndexes()}) \
            or list(range(self.proxy.rowCount()))
        lines = ["\t".join(COLUMNS)]
        for row in rows:
            source_row = self.proxy.mapToSource(self.proxy.index(row, 0)).row()
            hop = self.model_.hops[source_row]
            lines.append("\t".join(self.model_.text(hop, c) for c in range(len(COLUMNS))))
        text = "\n".join(lines) + "\n"
        QGuiApplication.clipboard().setText(text)
        return text
