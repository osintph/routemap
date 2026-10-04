"""The window's pure parts (route layout, the world map) and an offscreen smoke run.

Skipped where PySide6 is not installed: the engine is tested without Qt on
purpose, because FalconEye installs it without Qt.
"""
import json
import os
import pathlib

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from routemap.gui import geometry, mapview  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "gui"


def _route(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())["route"]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_the_bundled_world_loads_and_covers_the_globe():
    world = geometry.world()
    lons = [lon for ring in world["land"] for lon, _ in ring]
    lats = [lat for ring in world["land"] for _, lat in ring]
    assert len(world["land"]) > 1000 and world["borders"]
    assert min(lons) <= -179 and max(lons) >= 179
    assert min(lats) < -80 and max(lats) > 80
    assert "Natural Earth" in world["source"]


def test_a_pacific_crossing_is_unwrapped_not_drawn_the_long_way_round():
    """Hong Kong to San Jose must step east across 180, not west across Asia."""
    groups = mapview.route_groups(_route("amazon_route"))
    for before, after in zip(groups, groups[1:]):
        assert abs(after["lon"] - before["lon"]) <= 180, (before["hops"][0]["hop"],
                                                          after["hops"][0]["hop"])
    san_jose = next(g for g in groups if g["hops"][0]["hop"] == 13)
    assert san_jose["lon"] > 180


def test_consecutive_hops_in_one_place_share_a_marker_and_gaps_are_marked():
    groups = mapview.route_groups(_route("amazon_route"))
    labels = [mapview.hop_range(g["hops"]) for g in groups]
    assert "1-3" in labels and "14-15" in labels
    assert groups[0]["at_origin"]
    after_gap = next(g for g in groups if g["hops"][0]["hop"] == 11)
    assert after_gap["gap_before"], "hops 9 and 10 were silent; the segment must say so"


def test_an_ecmp_marker_explains_both_routers():
    route = _route("heise_ecmp_route")
    group = next(g for g in mapview.route_groups(route)
                 if any(h["hop"] == 8 for h in g["hops"]))
    tip = mapview.group_tooltip(group)
    assert "mei-b6-link" in tip and "sng-b6-link" in tip
    assert "ruled out" in tip and "used" in tip


@pytest.mark.parametrize("name", ["heise_ecmp_route", "amazon_route"])
def test_after_decluttering_no_two_markers_overlap(app, name):
    from routemap.gui import theme
    scene = mapview.build_scene(theme.LIGHT)
    rect, items = mapview.draw_route(scene, _route(name), theme.LIGHT, "dest")
    markers = mapview.markers_of(items)
    source = mapview.padded(rect, 16 / 9)
    k = 1600 / source.width()

    def to_device(point):
        from PySide6.QtCore import QPointF
        return QPointF((point.x() - source.left()) * k, (point.y() - source.top()) * k)

    mapview.declutter(markers, to_device)
    boxes = [m.footprint().translated(to_device(m.pos()) + m.offset) for m in markers]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert not a.intersects(b), "two markers still overlap"


def test_the_window_opens_loads_a_fixture_and_renders(app, tmp_path):
    from routemap.gui.mainwindow import MainWindow
    window = MainWindow()
    window.show()
    window.show_result(_route("amazon_route"), "amazon.com", ["traceroute", "amazon.com"])
    app.processEvents()
    assert window.table.model().rowCount() == 18
    assert "6" in window.unplaced.toggle.text()
    assert not window.grab().isNull()
    image = mapview.render_png(_route("heise_ecmp_route"), title="t", provenance="p")
    assert (image.width(), image.height()) == (1600, 900)
    window.close()


def test_the_gui_package_names_nothing_but_itself():
    """The product name comes from __about__, not from the GUI code."""
    gui = pathlib.Path(mapview.__file__).parent
    for path in gui.glob("*.py"):
        assert "Route Map" not in path.read_text(encoding="utf-8").split('"""', 2)[-1], path.name


def _window(app):
    from routemap.gui.mainwindow import MainWindow
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    app.processEvents()
    return window


def test_a_live_trace_draws_every_hop_and_keeps_the_legend_readable(app):
    """Found on a real trace: redrawing per hop left the legend measured empty."""
    route = _route("amazon_route")
    window = _window(app)
    window.show_tracing("amazon.com", ["traceroute", "amazon.com"])
    assert not window.map.card.isVisible(), "nothing may cover the map while tracing"
    for n in range(1, len(route["hops"]) + 1):
        window.update_live(dict(route, hops=route["hops"][:n]), "amazon.com", f"hop {n}")
        app.processEvents()
        assert window.table.model().rowCount() == n
    window.show_result(route, "amazon.com", ["traceroute", "amazon.com"], keep_view=True)
    app.processEvents()
    assert window.map.legend.width() > 120 and window.map.legend.height() > 60
    assert not window.live.body.isVisible(), "tool output is collapsed by default"
    window.close()


def test_selection_follows_both_ways_and_esc_clears(app):
    route = _route("amazon_route")
    window = _window(app)
    window.show_result(route, "amazon.com", ["traceroute", "amazon.com"])
    app.processEvents()
    collapsed = next(m for m in window.map.markers if m.hops == [14, 15])
    collapsed.clicked.emit(collapsed.hops)
    assert window.table.selected_hops() == [14, 15], "a collapsed marker selects all its rows"
    assert collapsed.selected
    window.table.select_hops([5])
    window.table.hopsSelected.emit([5])
    assert [m.hops for m in window.map.markers if m.selected] == [[5, 6]]
    window.clear_selection()
    assert window.table.selected_hops() == [] and not any(m.selected for m in window.map.markers)
    window.close()


def test_country_only_hops_are_hollow_labelled_and_not_in_the_fit(app):
    from routemap.gui import theme
    route = _route("heise_ecmp_route")
    country = [h for h in route["hops"] if h.get("precision") == "country"]
    assert country, "fixture lost its country-only hops"
    scene = mapview.build_scene(theme.LIGHT)
    rect, items = mapview.draw_route(scene, route, theme.LIGHT, "heise.de")
    hollow = [m for m in mapview.markers_of(items) if m.hollow]
    assert {n for m in hollow for n in m.hops} == {h["hop"] for h in country}
    assert all(m.caption and m.caption.endswith("(country only)") for m in hollow)
    # The fit is the same with the country-only hops as without them.
    without = dict(route, hops=[dict(h, lat=None, lon=None) if h.get("precision") == "country"
                                else h for h in route["hops"]])
    rect_without, _ = mapview.draw_route(mapview.build_scene(theme.LIGHT), without, theme.LIGHT)
    assert rect == rect_without, "a country centroid stretched the fit"
    # And a country-only hop far from everything else does not drag the view there.
    far = dict(route, hops=route["hops"] + [dict(country[0], hop=99, lat=-25.0, lon=134.0,
                                                 place="AU")])
    rect_far, _ = mapview.draw_route(mapview.build_scene(theme.LIGHT), far, theme.LIGHT)
    assert rect_far == rect
    from routemap.gui.hoptable import HopModel
    model = HopModel()
    model.set_hops(route["hops"])
    hop = country[0]
    # The Source column names the tier that answered: RIPEstat online when the
    # DB-IP City file is not installed, DB-IP when it is.
    assert model.text(hop, 2) == "ip-db (RIPEstat, online), country only"
    assert model.text(dict(hop, ip_provider="dbip"), 2) == "ip-db (DB-IP), country only"
    assert model.text(hop, 1).endswith("(country only)")


def test_silent_hops_after_the_last_placed_one_show_at_once(app):
    route = _route("amazon_route")
    groups = mapview.route_groups(route)
    assert groups[-1]["silent"] and [h["hop"] for h in groups[-1]["hops"]] == [16, 17, 18]
    partial = dict(route, hops=route["hops"][:10])  # hops 9 and 10 have not answered yet
    assert mapview.route_groups(partial)[-1]["silent"]


def test_marker_hover_has_the_row_fields(app):
    route = _route("heise_ecmp_route")
    group = next(g for g in mapview.route_groups(route) if any(h["hop"] == 6 for h in g["hops"]))
    tip = mapview.group_tooltip(group)
    for field in ("Hop", "Hostname", "IP address", "RTT", "Loss", "Source", "hnk-b4-link"):
        assert field in tip, field


def test_the_view_stops_following_once_the_user_moves_it(app):
    route = _route("amazon_route")
    window = _window(app)
    window.map.set_route(dict(route, hops=route["hops"][:3]), keep_view=True)
    window.map.zoom(2.0)                       # the user zooms
    assert window.map.user_moved
    before = window.map.transform().m11()
    window.map.set_route(route, keep_view=True)
    assert window.map.transform().m11() == before, "the view jumped after the user zoomed"
    window.map.fit_route()                     # Fit hands control back
    assert not window.map.user_moved
    window.close()


def test_help_menu_support_shows_every_donation_option_in_order(app):
    """Help > Support Route Map lists the donation options, in the agreed order,
    with the full crypto addresses; it is a dialog opened only from the menu."""
    from routemap.__about__ import DONATE_ADDRESSES, DONATE_LINKS
    from routemap.gui import dialogs
    from routemap.gui.mainwindow import MainWindow
    window = MainWindow()
    help_menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Help")
    assert "Support Route Map" in [a.text() for a in help_menu.actions()]
    assert [n for n, _ in DONATE_LINKS] == ["Ko-fi", "PayPal"]
    assert [n for n, _ in DONATE_ADDRESSES] == ["Bitcoin", "Monero"]
    dialog = dialogs.SupportDialog(window)
    for name, address in DONATE_ADDRESSES:
        assert dialog.address_fields[name].text() == address
    text = " ".join(label.text() for label in dialog.findChildren(dialogs.QLabel))
    assert text.index("ko-fi.com/osintph") < text.index("paypal.me/osintph")
    assert "sponsors" not in text.lower()
    dialog.close()
    window.close()


def test_the_app_does_not_link_the_site_until_it_is_approved(app, monkeypatch):
    """SITE_LINKED is the one switch: off, no getroutemap.app link anywhere in the app."""
    from routemap import __about__
    from routemap.gui import dialogs
    from routemap.gui.mainwindow import MainWindow
    window = MainWindow()
    if not __about__.SITE_LINKED:
        text = " ".join(label.text() for label in dialogs.SupportDialog(window).findChildren(dialogs.QLabel))
        assert __about__.SITE_URL not in text and "getroutemap.app/" not in text
    window.close()


# ------------------------------------------------------------------- 0.2.0 ---

def _sample_route():
    from importlib import resources

    from routemap_engine import OFFLINE, analyse_sync
    text = resources.files("routemap.gui").joinpath("data/sample_trace.txt").read_text("utf-8")
    return analyse_sync(text, (14.6, 121.0), sources=OFFLINE).to_dict()


def test_both_projections_draw_the_same_route_and_switching_keeps_it(app):
    from routemap.gui.mappane import MapPane
    route = _sample_route()
    pane = MapPane()
    pane.resize(900, 600)
    pane.show()
    pane.set_route(route, "heise.de")
    app.processEvents()
    assert pane.flat.markers and not pane.flat.ghost_markers
    pane.set_projection("globe")
    app.processEvents()
    image = pane.grab()
    assert not image.isNull()
    pane.globe.grab()
    assert pane.globe._hits, "the globe drew no clickable markers"
    hit_hops = {n for _, hops, _ in pane.globe._hits for n in hops}
    assert hit_hops <= {h["hop"] for h in route["hops"]}
    pane.set_projection("flat")
    assert pane.flat.route is route and pane.globe.route is route


def test_a_globe_marker_click_reports_its_hops(app):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from routemap.gui.globeview import GlobeView
    view = GlobeView()
    view.resize(800, 600)
    view.show()
    view.set_route(_sample_route(), "heise.de")
    view.grab()                     # paints, which records where each marker is
    rect, hops, _ = view._hits[-1]
    got = []
    view.markerClicked.connect(got.append)
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        view.event(QMouseEvent(kind, rect.center(), rect.center(), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    assert got == [hops]


def test_the_orthographic_projection_round_trips_and_hides_the_far_side():
    from routemap.gui.globeview import Ortho
    proj = Ortho(20.0, 100.0, 400, 300, 250)
    x, y, vis = proj.project(14.6, 121.0)
    assert vis
    lat, lon = proj.invert(x, y)
    assert lat == pytest.approx(14.6, abs=1e-6) and lon == pytest.approx(121.0, abs=1e-6)
    x, y, vis = proj.project(-20.0, -80.0)
    assert not vis and ((x - 400) ** 2 + (y - 300) ** 2) ** 0.5 == pytest.approx(250, abs=1e-6)


def test_replay_ends_with_the_whole_route_and_the_view_untouched(app):
    import time

    from routemap.gui import mappane
    route = _sample_route()
    pane = mappane.MapPane()
    pane.resize(900, 600)
    pane.show()
    pane.set_route(route, "heise.de")
    app.processEvents()
    before = pane.flat.transform()
    moved_before = pane.flat.user_moved
    pane.replay()
    assert pane.replaying
    deadline = time.time() + mappane.REPLAY_SECONDS + 4
    while pane.replaying and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    assert not pane.replaying
    assert len(pane.flat.route["hops"]) == len(route["hops"])
    assert pane.flat.transform() == before and pane.flat.user_moved == moved_before


def test_a_comparison_ghosts_the_old_run_and_rings_changed_hops(app):
    from routemap.gui.mappane import MapPane
    from routemap_engine import diff
    old = _sample_route()
    new = json.loads(json.dumps(old))
    new["hops"] = [h for h in new["hops"] if h["hop"] not in (8, 9)]   # Marseille and Paris gone
    d = diff.diff_routes(old, new)
    assert "Marseille" in d["summary"] and "gone" in d["summary"]
    pane = MapPane()
    pane.set_route(new, "heise.de")
    pane.set_comparison(old, d["new_marks"])
    assert pane.flat.ghost_markers and all(m.opacity() < 1 for m in pane.flat.ghost_markers)
    assert not set(pane.flat.ghost_markers) & set(pane.flat.markers)
    pane.set_comparison(None, None)
    assert not pane.flat.ghost_markers


def test_rtt_colours_follow_the_thresholds(app):
    from routemap.gui import theme
    scene = mapview.build_scene(theme.LIGHT)
    route = _sample_route()
    _, items = mapview.draw_route(scene, route, theme.LIGHT, quiet_ms=1000, hot_ms=2000)
    lines = [i for i in items if not isinstance(i, mapview.MarkerItem)]
    solid = [i.pen().color().name() for i in lines if i.pen().style() == Qt.SolidLine]
    assert solid and set(solid) == {theme.LIGHT.route_quiet.name()}, "every step is quiet at 1000 ms"


def test_settings_round_trip_the_new_fields(app):
    from routemap.config import Settings
    from routemap.gui.dialogs import SettingsDialog
    s = Settings()
    dialog = SettingsDialog(None, s)
    dialog.online.setChecked(False)
    assert not dialog.use_hoiho.isEnabled() and not dialog.use_ptr.isEnabled()
    dialog.projection.setCurrentIndex(1)
    dialog.rtt_quiet.setValue(20)
    dialog.rtt_hot.setValue(80)
    dialog.sensitive.setText("sg, xx1, cn")
    dialog.falconeye.setText("https://falcon.example.org/")
    problems = dialog.values_into(s)
    assert (s.online_lookups, s.projection, s.rtt_quiet_ms, s.rtt_hot_ms) == (False, "globe", 20, 80)
    assert s.sensitive_countries == ["CN", "SG"] and any("XX1" in p for p in problems)
    assert s.falconeye_url == "https://falcon.example.org"
    assert "not installed" in dialog.data_label.text()


def test_the_summary_panel_and_hop_details_show_offline_insight(app):
    from routemap import config, insight
    from routemap.gui.insightpanel import HopDetails, InsightPanel
    route = _sample_route()
    ins = insight.offline(route, config.Settings(sensitive_countries=["SG"]))
    ins["online"] = {"status": insight.OFF}
    panel = InsightPanel()
    panel.show_summary(route, ins, origin_cc="PH")
    assert "AS1299" in panel.sections["path"][1].text()
    assert "sensitive" in panel.sections["countries"][1].text()
    assert "Online lookups" in panel.sections["status"][1].text()
    details = HopDetails()
    hop = next(h for h in route["hops"] if h["hop"] == 7)
    details.show_hop(hop, ins, {"rir": None, "abuse": None, "status": insight.OFF})
    assert "AS1299" in details.rows["ASN"].text() and details.falcon.isEnabled()
    local = route["hops"][0]
    details.show_hop(local, ins, None)
    assert not details.falcon.isEnabled()


def test_the_map_credits_db_ip_as_soon_as_offline_asns_are_shown(app):
    """Regression: the credit line was set when the route was drawn, before the
    offline step added DB-IP ASNs, so it lacked DB-IP with Online lookups off."""
    from routemap import config
    from routemap.gui.app import Controller
    from routemap.gui.mainwindow import MainWindow
    window = MainWindow()
    controller = Controller(window, config.Settings(online_lookups=False, city_db_declined=True))
    route = _sample_route()
    controller.current = {"route": route, "target": "heise.de", "trace_text": "", "argv": None,
                          "source": "file", "origin_how": "coords", "when": None}
    window.show_result(route, "heise.de", None)
    assert "DB-IP" not in window.map.flat.attribution.text()
    controller._after_result()
    assert "DB-IP" in window.map.flat.attribution.text()
    assert "DB-IP" in window.map.globe.attribution.text()
    window.close()
