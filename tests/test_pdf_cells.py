"""No text in a PDF table cell is bigger than its cell (0.4.0): found in the
Phase 1 renders, where a 39-character IPv6 address was cut off in the Hops
table because it has no space or hyphen to wrap at. The check covers every
cell of every table in a report with paths, a reverse trace and IPv6 hops,
not only the address column."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QFontMetricsF, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from routemap.gui import report  # noqa: E402

V6 = "2a02:2e0:3fe:1001:302:ffff:abcd:1234"      # 36 characters
LONGEST = "2001:2000:3080:1e94:ffff:ffff:ffff:ffff"   # 39, the longest an IPv6 address prints


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _route():
    hops = []
    for n, addr in enumerate(["fd00::1", "2001:4450:1:2::1", LONGEST, V6], 1):
        hops.append({"hop": n, "address": addr, "addresses": [addr, LONGEST] if n == 3 else [addr],
                     "hostname": None, "hostnames": [], "min_rtt_ms": 10.0 * n, "avg_rtt_ms": 11.0 * n,
                     "sent": 3, "lost": 0, "loss_pct": 0.0, "codes": [], "source": "ip-db",
                     "lat": 50.0 + n, "lon": 8.0 + n, "place": "Frankfurt am Main, DE", "cc": "DE",
                     "annotations": [], "candidates": []})
    located = [{"hop": h["hop"], "address": h["address"], "hostname": None, "lat": h["lat"], "lon": h["lon"],
                "place": h["place"], "cc": "DE", "source": "ip-db", "min_rtt_ms": 1.0, "avg_rtt_ms": 1.0,
                "reason": None} for h in hops]
    alt = [dict(h) for h in located]
    alt[2]["address"] = "2001:2000:3080:22a1:ffff:ffff:ffff:ffff"
    paths = {"method": "icmp-paris", "at_least": True, "af": 6, "per_packet_hops": [], "probes_sent": 300,
             "flows": 24, "paths_capped": False, "stopped_by": "complete", "seconds": 30.0,
             "paths": [{"id": "A", "flows": list(range(12)), "hops": [h["address"] for h in located],
                        "rtt_ms": [1.0] * 4, "reached": True, "sent": 10, "lost": 0, "loss_pct": 0.0,
                        "rtt_to_target_ms": 250.0, "located": located},
                       {"id": "B", "flows": list(range(12, 24)), "hops": [h["address"] for h in alt],
                        "rtt_ms": [1.0] * 4, "reached": True, "sent": 10, "lost": 1, "loss_pct": 10.0,
                        "rtt_to_target_ms": 252.0, "located": alt}]}
    return {"parser": "icmp", "parser_label": "Built-in ICMP prober", "target": "heise.de", "warnings": [],
            "hoiho_ruleset_date": None, "origin": {"lat": 14.6, "lon": 121.0, "label": "Manila", "source": "supplied"},
            "hops": hops, "paths": paths}


def test_no_pdf_table_cell_overflows(app, tmp_path, monkeypatch):
    drawn = []

    class Recording(QPainter):
        def drawText(self, *args):
            if len(args) == 3 and isinstance(args[0], QRectF):
                drawn.append((QRectF(args[0]), args[1], args[2], QFontMetricsF(self.font(), self.device())))
            return super().drawText(*args)
    monkeypatch.setattr(report, "QPainter", Recording)
    route = _route()
    seg = {"hops": [route["hops"][2]], "asn": 1299, "place": "Paris, FR"}
    cmp = {"rows": [{"forward": seg, "reverse": seg, "same": True}], "summary": "Both directions go through"
           " the same networks and places.", "differs": False}
    rev = {"measurement_id": 1, "probe": {"id": 6001}, "route": route}
    report.write_pdf(str(tmp_path / "r.pdf"), route, target="heise.de", trace_text="", tool_label="icmp-paris",
                     origin_how="ip", source="paths", reverse=rev, reverse_cmp=cmp)
    cells = [d for d in drawn if d[2]]
    assert any(LONGEST in text for _, _, text, _ in cells)
    for rect, flags, text, metrics in cells:
        need = metrics.boundingRect(rect, flags, text)
        assert need.width() <= rect.width() + 0.5 and need.height() <= rect.height() + 0.5, text
