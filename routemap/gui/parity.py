"""
The rendered window's structure, for comparing platforms: which panels show,
what the legends say, which chart series have data, which table columns
exist, what the map draws, and the look (style, font, accent). Not pixels:
fonts rasterise differently, structure must not.

Written (4 Oct 2026) after the same release showed different panels on
Windows and macOS. tests/test_parity.py compares a recorded trace's snapshot
with one reference on every OS; the packaged build's smoke test writes
parity.json and the release summary requires every platform's to match.
"""
from __future__ import annotations


def snapshot(window) -> dict:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from routemap.gui import mapview, theme
    from routemap.gui.globeview import legend_rows

    app = QApplication.instance()
    ins = window.insight
    sections = {key: content.isVisible() for key, (_, content) in ins.sections.items()}
    headings = {key: head.text() for key, (head, _) in ins.sections.items() if head.isVisible()}
    flat = window.map.flat
    legend = []
    for i in range(flat.legend_layout.count()):
        widget = flat.legend_layout.itemAt(i).widget()
        if widget is None:
            continue
        from PySide6.QtWidgets import QLabel
        texts = [w.text() for w in widget.findChildren(QLabel) if w.text()] if not isinstance(widget, QLabel) \
            else [widget.text()]
        legend += [t for t in texts if t and "- -" not in t]
    route = flat.route or {}
    model = window.table.model_
    bars = ins.sections["updates"][1]
    spark = ins.sections["rtt"][1]
    spark_hops = spark.hops
    font = app.font()
    return {
        "style": app.property("routemapStyle"),
        "font": {"family": font.family(), "pixel_size": font.pixelSize(),
                 # Widgets the platform gives its own font (macOS: tool buttons, headers).
                 "tool_button": QApplication.font("QToolButton").pixelSize(),
                 "header": QApplication.font("QHeaderView").pixelSize(),
                 "map_marker": flat.markers[0].font.pixelSize() if flat.markers else None},
        "accent": theme.ACCENT["dark" if theme.is_dark() else "light"],
        "sections": sections,
        "headings": headings,
        "panels": {"tool_output_expanded": window.live.toggle.isChecked(),
                   "unplaced_expanded": window.unplaced.toggle.isChecked(),
                   "hop_details_visible": window.details.isVisible()},
        "legend": legend,
        "globe_legend": [text for _, text in legend_rows(route, flat.palette_, flat.quiet_ms, flat.hot_ms)],
        "charts": {"bgp_bins": len(bars.bins), "bgp_total": sum(bars.bins),
                   "rtt_points": sum(1 for h in spark_hops if h.get("min_rtt_ms") is not None),
                   "floor_points": sum(1 for h in spark_hops if h.get("distance_km") is not None)},
        "table": {"columns": [model.headerData(c, Qt.Horizontal) for c in range(model.columnCount())],
                  "rows": model.rowCount()},
        "map": {"markers": len(flat.markers),
                "multi_responder_hops": sorted(h["hop"] for h in route.get("hops") or []
                                               if len(h.get("addresses") or []) > 1),
                "origin_marker": any(getattr(m, "origin", False) for m in flat.markers),
                "credit": flat.attribution.text(),
                "groups": len(mapview.route_groups(route))},
    }
