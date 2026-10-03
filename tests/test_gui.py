"""The window's pure parts (route layout, the world map) and an offscreen smoke run.

Skipped where PySide6 is not installed: the engine is tested without Qt on
purpose, because FalconEye installs it without Qt.
"""
import json
import os
import pathlib

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF  # noqa: E402
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
    rect, markers = mapview.draw_route(scene, _route(name), theme.LIGHT, "dest")
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
