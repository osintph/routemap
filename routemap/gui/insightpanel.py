"""
The route summary beside the hop table, and the details of one hop.

Both only display what routemap.insight produced. The summary shows the AS
path with RPKI badges, the countries crossed, a typical latency for the trip
(RIPE Atlas), what RIPE's route collectors see for the destination prefix, the
last 48 hours of BGP updates for it, and the RTT of every hop against the
lowest RTT physics allows for where it was placed.

Anything online says where it came from, and says "unavailable" when a source
did not answer; with Online lookups off it says that instead of going blank.
"""
from __future__ import annotations

import html

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from routemap import insight as insight_mod
from routemap.gui import theme
from routemap.gui.text import markup, plain
from routemap_engine import geo

BADGE = {"valid": ("#0f7a50", "#e3f4ec"), "invalid": ("#b42318", "#fde8e6"),
         "unknown": ("#8a5a00", "#fdf1dc"), "info": ("#33506e", "#e6edf5"),
         "sensitive": ("#8a2c0d", "#fde6dc")}
BADGE_DARK = {"valid": ("#7fe0b4", "#123327"), "invalid": ("#ff9b91", "#3d1512"),
              "unknown": ("#f0c070", "#3a2c10"), "info": ("#a9c4e4", "#1a2a3b"),
              "sensitive": ("#ffb08f", "#3d1d10")}


def badge(text: str, kind: str) -> str:
    fg, bg = (BADGE_DARK if theme.is_dark() else BADGE).get(kind, BADGE["info"])
    return (f"<span style='color:{fg}; background-color:{bg}; font-weight:600;'>"
            f"&nbsp;{html.escape(text)}&nbsp;</span>")


def _muted(text: str) -> str:
    return f"<span style='color:{theme.current().overlay_muted.name()}'>{text}</span>"


def heading(text: str) -> QLabel:
    label = QLabel(text.upper())
    # Headings name things from the data (a prefix, a comparison): plain text.
    label.setTextFormat(Qt.PlainText)
    label.setStyleSheet("font-size: 10px; font-weight: 700; letter-spacing: 1px;"
                        f"color: {theme.current().overlay_muted.name()};")
    return label


def rich(text: str = "") -> QLabel:
    """A label for markup this module builds, with every data value escaped.
    It opens no links: nothing in the panel links anywhere, and a link that
    came from data must not open a file or a URL scheme on one click (RM-01)."""
    label = QLabel(text)
    label.setTextFormat(Qt.RichText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    label.setOpenExternalLinks(False)
    label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    return label


class UpdateBars(QWidget):
    """BGP updates per hour over the last 48 hours, oldest left."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bins: list[int] = []
        self.setMinimumHeight(56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_bins(self, bins: list):
        """Counts per hour, oldest first; None for hours RIPEstat has no data
        for yet (its route-collector data runs a few hours behind)."""
        self.bins = list(bins or [])
        self.update()

    def sizeHint(self):
        return QSize(320, 56)

    def paintEvent(self, event):
        if not self.bins:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = theme.current()
        w, h = self.width(), self.height() - 16
        bw = w / len(self.bins)
        top = max([n for n in self.bins if n is not None] or [1]) or 1
        pending = [i for i, n in enumerate(self.bins) if n is None]
        if pending:
            # Not yet available: a hatched band, not empty bars.
            x0 = pending[0] * bw
            band = QRectF(x0, 0, w - x0, h)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(pal.coast, Qt.BDiagPattern))
            p.drawRect(band)
        for i, n in enumerate(self.bins):
            if n is None:
                continue
            bar = h * n / top
            p.setPen(Qt.NoPen)
            p.setBrush(pal.sources["ip-db"] if n else pal.coast)
            p.drawRect(QRectF(i * bw + 1, h - max(bar, 1.5), max(1.0, bw - 2), max(bar, 1.5)))
        font = QFont()
        font.setPixelSize(11)
        p.setFont(font)
        p.setPen(pal.overlay_muted)
        p.drawText(QRectF(0, h + 2, w, 14), Qt.AlignLeft, "48 h ago")
        p.drawText(QRectF(0, h + 2, w, 14), Qt.AlignRight, "trace time")
        p.end()


class RttSparkline(QWidget):
    """Measured minimum RTT per hop (solid) against the lowest RTT physics allows
    for where the hop was placed (dashed: distance from the origin at 100 km
    per ms of round trip). A hop far above the floor spent its time somewhere
    the map cannot show: queues, a detour, a slow reply path."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hops: list[dict] = []
        self.setMinimumHeight(86)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_hops(self, hops: list[dict]):
        self.hops = list(hops or [])
        self.update()

    def sizeHint(self):
        return QSize(320, 86)

    def paintEvent(self, event):
        points = [(h.get("min_rtt_ms"), h.get("distance_km")) for h in self.hops]
        top = max([r for r, _ in points if r is not None] +
                  [d / geo.KM_PER_MS_ROUND_TRIP for _, d in points if d is not None] + [1.0])
        if len(points) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = theme.current()
        w, h = self.width() - 8, self.height() - 18
        sx = w / (len(points) - 1)
        floor = [QPointF(4 + i * sx, h - h * (d / geo.KM_PER_MS_ROUND_TRIP) / top + 4)
                 for i, (_, d) in enumerate(points) if d is not None]
        rtt = [QPointF(4 + i * sx, h - h * r / top + 4) for i, (r, _) in enumerate(points) if r is not None]
        pen = QPen(pal.route_gap, 1.5, Qt.DashLine)
        p.setPen(pen)
        for a, b in zip(floor, floor[1:]):
            p.drawLine(a, b)
        p.setPen(QPen(pal.sources["hoiho"], 2))
        for a, b in zip(rtt, rtt[1:]):
            p.drawLine(a, b)
        p.setPen(Qt.NoPen)
        p.setBrush(pal.sources["hoiho"])
        for q in rtt:
            p.drawEllipse(q, 2.4, 2.4)
        font = QFont()
        font.setPixelSize(11)
        p.setFont(font)
        p.setPen(pal.overlay_muted)
        p.drawText(QRectF(4, h + 5, w, 14), Qt.AlignLeft, f"{top:.0f} ms at the top")
        p.end()


RTT_NOTE = ("Solid: measured minimum RTT. Dashed: the lowest RTT the placement allows "
            "(100 km per ms of round trip).")


class InsightPanel(QScrollArea):
    """The route summary. Fed by show(route, insight, ...)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        self.box = QVBoxLayout(body)
        self.box.setContentsMargins(2, 2, 8, 2)
        self.box.setSpacing(4)
        self.sections: dict[str, tuple[QLabel, QWidget]] = {}
        for key, title in (("diff", "Compared with"), ("path", "AS path"), ("countries", "Countries transited"),
                           ("anycast", "Destination"), ("loss", "Loss"),
                           ("baseline", "Typical latency (RIPE Atlas)"),
                           ("ris", "BGP view (RIPE RIS)"), ("updates", "BGP updates, last 48 h"),
                           ("rtt", "RTT per hop and the physics floor"), ("status", "")):
            head = heading(title)
            if key == "updates":
                content = UpdateBars()
            elif key == "rtt":
                content = RttSparkline()
            else:
                content = rich()
            self.box.addWidget(head)
            self.box.addWidget(content)
            if key == "rtt":
                self.rtt_note = rich(_muted(RTT_NOTE))
                self.box.addWidget(self.rtt_note)
            if key == "updates":
                self.updates_note = rich()
                self.box.addWidget(self.updates_note)
            self.sections[key] = (head, content)
        self.box.addStretch(1)
        self.setWidget(body)
        self.clear()

    def set_loss(self, text: str) -> None:
        """Only the Loss line, for a continuous session's running figures."""
        if text:
            self.sections["loss"][1].setText(html.escape(text))
            self.sections["loss"][1].setAccessibleName("Loss: " + text)
            self._show("loss", True)

    def _show(self, key: str, on: bool):
        head, content = self.sections[key]
        head.setVisible(on and bool(head.text()))
        content.setVisible(on)
        if key == "rtt":
            self.rtt_note.setVisible(on)
        if key == "updates":
            self.updates_note.setVisible(on and bool(self.updates_note.text()))

    def clear(self):
        for key in self.sections:
            self._show(key, False)

    def show_summary(self, route: dict, ins: dict | None, *, origin_cc: str | None = None,
                     diff: dict | None = None, diff_label: str = ""):
        s = insight_mod.summary(route, ins, origin_cc)
        # AS path
        if s["as_path"]:
            parts = []
            for step in s["as_path"]:
                name = f"<b>AS{html.escape(str(step['asn']))}</b> {html.escape(str(step['short']))}"
                if step.get("rpki"):
                    name += " " + badge(step["rpki"]["label"], step["rpki"]["state"])
                parts.append(name)
            local = any(h.get("source") == "local" for h in route.get("hops") or [])
            text = (_muted("local hops") + " &gt; " if local else "") + " &gt; ".join(parts)
            self.sections["path"][1].setText(text)
            self._show("path", True)
        else:
            self.sections["path"][1].setText(_muted("No AS numbers: no public addresses answered, "
                                                    "or the ASN database is missing."))
            self._show("path", True)
        # countries
        if s["countries"]:
            parts = []
            if s["origin_cc"]:
                parts.append(f"{s['origin_cc']} {_muted('(origin)')}")
            for c in s["countries"]:
                item = html.escape(str(c["cc"])) + (" " + _muted("(country only)") if c["country_only"] else "")
                if c["sensitive"]:
                    item += " " + badge("sensitive", "sensitive")
                parts.append(item)
            self.sections["countries"][1].setText(" &gt; ".join(parts))
            self._show("countries", True)
        else:
            self._show("countries", False)
        # anycast
        if s["anycast"]:
            self.sections["anycast"][1].setText(html.escape(s["anycast"]))
            self._show("anycast", True)
        else:
            self._show("anycast", False)
        # loss: the destination's, with the hops that only rate-limit named
        loss = s.get("loss") or {}
        if loss.get("text"):
            self.sections["loss"][1].setText(html.escape(loss["text"]))
            self.sections["loss"][1].setAccessibleName("Loss: " + loss["text"])
            self._show("loss", True)
        else:
            self._show("loss", False)
        status = s["status"]
        off = status == insight_mod.OFF
        loading = status in ("loading", "partial")
        # baseline
        if isinstance(s["baseline"], dict):
            b = s["baseline"]
            self.sections["baseline"][1].setText(f"{html.escape(b['text'])} {badge(b['delta'], 'info')}<br>"
                                                 + _muted(html.escape(b["detail"])))
            self._show("baseline", True)
        elif s["baseline"] == insight_mod.UNAVAILABLE:
            why = s.get("reasons", {}).get("baseline")
            self.sections["baseline"][1].setText(_muted("unavailable" + (f": {html.escape(why)}" if why else "")))
            self._show("baseline", True)
        else:
            self._show("baseline", False)
        # RIS
        if s["ris"]:
            r = s["ris"]
            self.sections["ris"][0].setText(f"BGP VIEW OF {r['prefix']} (RIPE RIS)")
            lines = [html.escape(x) for x in r["lines"]]
            vis = html.escape(r["visibility"]) if r["visibility"] else ""
            if r["low_visibility"]:
                vis += " " + badge("low visibility", "unknown")
            if r.get("rpki"):
                vis += " " + badge(r["rpki"]["label"], r["rpki"]["state"])
            if vis:
                lines.append(vis)
            self.sections["ris"][1].setText("<br>".join(lines))
            self._show("ris", True)
        elif s.get("reasons", {}).get("prefix"):
            self.sections["ris"][0].setText("BGP VIEW (RIPE RIS)")
            self.sections["ris"][1].setText(_muted("unavailable: " + html.escape(s["reasons"]["prefix"])))
            self._show("ris", True)
        else:
            self._show("ris", False)
        # updates
        updates = s["updates"]
        if updates:
            self.sections["updates"][0].setText(f"BGP UPDATES, LAST 48 H ({updates['total']})"
                                                + (f", BURST OF {updates['burst']} AT TRACE TIME"
                                                   if updates.get("burst") else ""))
            self.sections["updates"][1].set_bins(updates["bins"])
            pending = sum(1 for n in updates["bins"] if n is None)
            self.updates_note.setText(_muted(
                f"Hatched: the last {pending} h, which RIPEstat's data does not reach yet "
                f"(it runs to {html.escape(updates['until'][11:16])} UTC)") if pending and updates.get("until") else "")
            self._show("updates", True)
        elif s.get("reasons", {}).get("updates"):
            # Never just gone: the heading stays, with why there are no bars.
            self.sections["updates"][0].setText("BGP UPDATES, LAST 48 H")
            self.sections["updates"][1].set_bins([])
            self.updates_note.setText(_muted("unavailable: " + html.escape(s["reasons"]["updates"])))
            self._show("updates", True)
        else:
            self.updates_note.setText("")
            self._show("updates", False)
        # sparkline
        hops = route.get("hops") or []
        self.sections["rtt"][1].set_hops(hops)
        if s.get("reasons", {}).get("origin"):
            self.rtt_note.setText(_muted("Solid: measured minimum RTT. No dashed physics floor: "
                                         + html.escape(s["reasons"]["origin"]) + "."))
        else:
            self.rtt_note.setText(_muted(RTT_NOTE))
        self._show("rtt", sum(1 for h in hops if h.get("min_rtt_ms") is not None) >= 2)
        # diff
        if diff:
            self.sections["diff"][0].setText(f"COMPARED WITH {diff_label}".upper())
            self.sections["diff"][1].setText(html.escape(diff["summary"]))
            self._show("diff", True)
        else:
            self._show("diff", False)
        # status
        if off:
            note = "Online details are off (Settings › Sources › Online lookups)."
        elif loading:
            note = "Asking RIPEstat and RIPE Atlas…"
        elif status and status.startswith(insight_mod.UNAVAILABLE):
            note = "Online details unavailable: RIPEstat did not answer in time."
        else:
            note = ""
        self.sections["status"][1].setText(_muted(note))
        self._show("status", bool(note))


class HopDetails(QFrame):
    """One hop, in full: placement, network, RPKI, RIR, abuse contact."""

    openFalconEye = Signal(str)       # the address

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        top = QHBoxLayout()
        self.title = markup()
        self.title.setTextFormat(Qt.RichText)
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top.addWidget(self.title, 1)
        self.falcon = QPushButton("Open in FalconEye")
        self.falcon.setToolTip("Opens IP Reputation in FalconEye and copies this address to "
                               "paste there. Nothing is sent until you run the lookup.")
        self.falcon.clicked.connect(lambda: self.openFalconEye.emit(self.address or ""))
        top.addWidget(self.falcon)
        layout.addLayout(top)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(3)
        layout.addLayout(self.grid)
        self.rows: dict[str, QLabel] = {}
        for i, key in enumerate(("Address", "Placed", "ASN", "Prefix", "RIR", "RPKI", "Abuse", "AS overview")):
            name = plain(key)
            name.setStyleSheet(f"color: {theme.current().overlay_muted.name()}; font-weight: 600;")
            value = rich()
            self.grid.addWidget(name, i, 0, Qt.AlignTop)
            self.grid.addWidget(value, i, 1)
            self.rows[key] = value
        self.copy_abuse = QToolButton()
        self.copy_abuse.setText("Copy")
        self.copy_abuse.clicked.connect(self._copy_abuse)
        self.grid.addWidget(self.copy_abuse, 6, 2, Qt.AlignTop)
        self.grid.setColumnStretch(1, 1)
        self.address: str | None = None
        self.abuse: list[str] = []
        self.hide()

    def _copy_abuse(self):
        if self.abuse:
            QGuiApplication.clipboard().setText(", ".join(self.abuse))
            self.copy_abuse.setText("Copied")
            QTimer.singleShot(1500, lambda: self.copy_abuse.setText("Copy"))

    def show_hop(self, hop: dict, ins: dict | None, extra: dict | None = None):
        """*extra*: {"rir", "abuse", "status"} from insight.hop_details, or None while loading."""
        ins = ins or {}
        online = ins.get("online") or {}
        detail = (online.get("hops") or {}).get(str(hop["hop"])) or {}
        public = next((a for a in hop.get("addresses") or [] if geo.classify_address(a) == "public"), None)
        self.address = public
        name = hop.get("hostname") or ""
        self.title.setText(f"<b>Hop {html.escape(str(hop['hop']))}</b>"
                           + (f" &middot; {html.escape(str(name))}" if name else ""))
        self.falcon.setEnabled(bool(public))
        r = self.rows
        r["Address"].setText(html.escape(", ".join(hop.get("addresses") or []) or "no answer"))
        if hop.get("lat") is not None:
            how = theme.SOURCE_LABELS.get(hop.get("source"), hop.get("source"))
            if hop.get("source") == "ip-db":
                how += " via " + ("DB-IP, offline" if hop.get("ip_provider") == "dbip" else "RIPEstat, online")
            budget = ""
            if hop.get("distance_km") is not None and hop.get("rtt_budget_km") is not None:
                budget = (f" ({hop['distance_km']:,.0f} km from the origin, within "
                          f"{hop['rtt_budget_km']:,.0f} km)")
            r["Placed"].setText(f"{html.escape(hop.get('place') or '')} by {html.escape(how)}{budget}")
        else:
            r["Placed"].setText(_muted(html.escape(hop.get("reason") or "not placed")))
        asn = hop.get("asn")
        if asn:
            org = hop.get("as_org") or ((online.get("asns") or {}).get(str(asn)) or {}).get(
                "overview", {}) or {}
            org = org if isinstance(org, str) else org.get("holder") or ""
            src = " " + _muted("(DB-IP)" if hop.get("asn_source") == "dbip" else "(RIPEstat)")
            r["ASN"].setText(f"AS{html.escape(str(asn))}, {html.escape(str(org))}{src}")
        else:
            r["ASN"].setText(_muted("none (local or no answer)" if not public else "unknown"))
        prefix = detail.get("prefix")
        rng = hop.get("as_network")
        r["Prefix"].setText((html.escape(prefix) if prefix else _muted("unavailable" if public else "n/a"))
                            + (" " + _muted(f"(DB-IP range {html.escape(rng)})") if rng and rng != prefix else ""))
        state = detail.get("rpki")
        if state and state != insight_mod.UNAVAILABLE:
            kind = "valid" if state == "valid" else ("invalid" if state.startswith("invalid") else "unknown")
            words = {"valid": "covered by a ROA for this origin",
                     "unknown": "no ROA covers this prefix"}.get(state, "a ROA exists and this announcement breaks it")
            r["RPKI"].setText(badge(insight_mod.RPKI_LABEL.get(state, state), kind) + " " + _muted(words))
        else:
            r["RPKI"].setText(_muted("unavailable" if public else "n/a"))
        if extra is None and public:
            r["RIR"].setText(_muted("asking RIPEstat…"))
            r["Abuse"].setText(_muted("asking RIPEstat…"))
            self.abuse = []
        else:
            extra = extra or {}
            status = extra.get("status")
            if status == insight_mod.OFF:
                r["RIR"].setText(_muted("Online lookups are off"))
                r["Abuse"].setText(_muted("Online lookups are off"))
                self.abuse = []
            else:
                rir = extra.get("rir")
                r["RIR"].setText(html.escape(rir) if rir and rir != insight_mod.UNAVAILABLE else _muted(
                    "unavailable" if public else "n/a"))
                abuse = extra.get("abuse")
                self.abuse = abuse if isinstance(abuse, list) else []
                r["Abuse"].setText(html.escape(", ".join(self.abuse)) if self.abuse else _muted(
                    "none published" if isinstance(abuse, list) else ("unavailable" if public else "n/a")))
        self.copy_abuse.setVisible(bool(self.abuse))
        ov = ((online.get("asns") or {}).get(str(asn)) or {}) if asn else {}
        n, o = ov.get("neighbours"), ov.get("overview")
        if n or o:
            text = []
            if o:
                text.append("announced" if o.get("announced") else "not announced")
            if n:
                text.append(f"{n['upstream']:,} upstream, {n['downstream']:,} downstream neighbours: {n['kind']}")
            r["AS overview"].setText(html.escape("; ".join(text)))
        else:
            r["AS overview"].setText(_muted("unavailable" if asn else "n/a"))
        self.show()
