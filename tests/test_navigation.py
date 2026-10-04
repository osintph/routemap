"""Zoom and pan: the limits and the fit as functions, then real events through
both views. Written for the 0.2.0 bug where pinch did nothing, a trackpad's
two-finger scroll zoomed instead of panning, and the wheel could not zoom out
after Fit; each test below fails on that code."""
import json
import pathlib

import pytest

from routemap.gui import navigation as nav

pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent, QNativeGestureEvent, QPointingDevice, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "gui"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------- the limits ---

@pytest.mark.parametrize("w,h", [(400, 300), (1200, 700), (3000, 400), (300, 2000)])
def test_the_smallest_scale_still_shows_the_whole_world_and_no_less(w, h):
    s = nav.min_scale(w, h)
    world_w, world_h = 360 * s * nav.SCENE_UNITS_PER_DEG, 180 * s * nav.SCENE_UNITS_PER_DEG
    assert world_w <= w + 1e-6 and world_h <= h + 1e-6
    assert world_w >= w - 1e-6 or world_h >= h - 1e-6, "at the floor the world fills one dimension"


def test_the_largest_scale_is_city_streets_not_buildings():
    assert nav.web_zoom(nav.max_scale()) == pytest.approx(nav.MAX_WEB_ZOOM)


@pytest.mark.parametrize("factor", [1e-6, 0.5, 2.0, 1e6])
def test_zoom_factor_never_leaves_the_limits(factor):
    for current in (nav.min_scale(800, 600), 3.0, nav.max_scale()):
        result = current * nav.zoom_factor(current, factor, 800, 600)
        assert nav.min_scale(800, 600) - 1e-9 <= result <= nav.max_scale() + 1e-9


def test_fit_frames_the_route_with_padding_and_stays_in_limits():
    w, h = 900, 600
    span_w, span_h = 120 * 4.0, 40 * 4.0          # 120 by 40 degrees
    s = nav.fit_scale(span_w, span_h, w, h)
    assert span_w * s < w and span_h * s < h
    assert span_w * s * (1 + 2 * nav.FIT_PAD) == pytest.approx(w, rel=1e-6) or \
        span_h * s * (1 + 2 * nav.FIT_PAD) == pytest.approx(h, rel=1e-6)
    one_city = nav.fit_scale(0, 0, w, h)
    assert one_city <= nav.max_scale() and nav.web_zoom(one_city) < nav.MAX_WEB_ZOOM
    world = nav.fit_scale(400 * 4.0, 200 * 4.0, w, h)
    assert world == pytest.approx(nav.min_scale(w, h))


@pytest.mark.parametrize("args,kind", [
    ((0, 120, 0, 0, False, False), "zoom"),      # mouse wheel notch
    ((0, -120, 0, 0, False, False), "zoom"),
    ((0, 12, 0, 6, False, True), "pan"),         # macOS trackpad two-finger scroll
    ((0, 24, 0, 0, False, True), "pan"),         # touchpad without pixel deltas
    ((0, 12, 0, 6, True, True), "zoom"),         # Ctrl+scroll, a Windows/Chrome pinch
    ((60, 0, 0, 0, False, False), "pan"),        # horizontal wheel
    ((0, 0, 0, 0, False, False), "none"),
])
def test_wheel_events_are_sorted_into_zoom_and_pan(args, kind):
    ax, ay, px, py, mod, pad = args
    assert nav.wheel_action(ax, ay, px, py, zoom_modifier=mod, touchpad=pad)[0] == kind


def test_a_gesture_step_cannot_collapse_or_flip_the_map():
    assert nav.gesture_factor(-5.0) == 0.5 and nav.gesture_factor(9.0) == 2.0
    assert nav.gesture_factor(0.1) == pytest.approx(1.1)


# ------------------------------------------------------------ the flat map ---

def _route():
    return json.loads((FIX / "heise_ecmp_route.json").read_text())["route"]


@pytest.fixture
def flat(app):
    from routemap.gui.mapview import MapView
    view = MapView()
    view.resize(900, 600)
    view.show()
    view.set_route(_route(), "heise.de")
    app.processEvents()
    return view


def _wheel(view, pos, angle=(0, 0), pixel=(0, 0), phase=Qt.NoScrollPhase, mods=Qt.NoModifier):
    vp = view.viewport() if hasattr(view, "viewport") else view
    g = QPointF(vp.mapToGlobal(pos.toPoint()))
    ev = QWheelEvent(pos, g, QPoint(*pixel), QPoint(*angle), Qt.NoButton, mods, phase, False)
    QApplication.sendEvent(vp, ev)
    QApplication.processEvents()


def _pinch(target, pos, value):
    ev = QNativeGestureEvent(Qt.ZoomNativeGesture, QPointingDevice.primaryPointingDevice(), 2, pos, pos,
                             QPointF(target.mapToGlobal(pos.toPoint())), value, QPointF(0, 0))
    QApplication.sendEvent(target, ev)
    QApplication.processEvents()


def test_the_mouse_wheel_zooms_around_the_cursor(flat):
    pos = QPointF(250, 200)
    before_scene = flat.mapToScene(pos.toPoint())
    k0 = flat.transform().m11()
    _wheel(flat, pos, angle=(0, 120))
    assert flat.transform().m11() == pytest.approx(k0 * nav.WHEEL_ZOOM_PER_NOTCH, rel=1e-3)
    after_scene = flat.mapToScene(pos.toPoint())
    assert abs(after_scene.x() - before_scene.x()) < 2 and abs(after_scene.y() - before_scene.y()) < 2


def test_the_wheel_can_zoom_out_after_fit_until_the_whole_world_shows(flat):
    flat.fit_route()
    k0 = flat.transform().m11()
    for _ in range(30):
        _wheel(flat, QPointF(450, 300), angle=(0, -120))
    k = flat.transform().m11()
    assert k < k0 and k == pytest.approx(nav.min_scale(flat.viewport().width(), flat.viewport().height()))


def test_a_trackpad_scroll_pans_and_does_not_zoom(flat):
    k0 = flat.transform().m11()
    flat.zoom(4)
    k1 = flat.transform().m11()
    centre = flat.mapToScene(flat.viewport().rect().center())
    _wheel(flat, QPointF(450, 300), angle=(0, 60), pixel=(40, 30), phase=Qt.ScrollUpdate)
    assert flat.transform().m11() == pytest.approx(k1)
    moved = flat.mapToScene(flat.viewport().rect().center())
    assert (moved - centre).manhattanLength() > 1
    assert k0 != k1


def test_a_trackpad_pinch_zooms_around_the_gesture(flat):
    k0 = flat.transform().m11()
    _pinch(flat.viewport(), QPointF(300, 250), 0.25)
    assert flat.transform().m11() == pytest.approx(k0 * 1.25, rel=1e-3)


def test_ctrl_wheel_zooms_even_from_a_touchpad(flat):
    k0 = flat.transform().m11()
    _wheel(flat, QPointF(450, 300), angle=(0, 120), pixel=(0, 30), phase=Qt.ScrollUpdate,
           mods=Qt.ControlModifier)
    assert flat.transform().m11() > k0


def test_keys_zoom_pan_and_reset(flat):
    flat.fit_route()
    k_fit = flat.transform().m11()
    for key in (Qt.Key_Plus, Qt.Key_Plus):
        QApplication.sendEvent(flat, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, "+"))
    assert flat.transform().m11() == pytest.approx(k_fit * nav.BUTTON_ZOOM ** 2, rel=1e-3)
    c0 = flat.mapToScene(flat.viewport().rect().center())
    QApplication.sendEvent(flat, QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier))
    assert flat.mapToScene(flat.viewport().rect().center()).x() > c0.x()
    QApplication.sendEvent(flat, QKeyEvent(QEvent.KeyPress, Qt.Key_0, Qt.NoModifier, "0"))
    assert flat.transform().m11() == pytest.approx(k_fit, rel=1e-3)


def test_double_click_zooms_in_one_step(flat):
    k0 = flat.transform().m11()
    pos = QPointF(400, 300)
    ev = QMouseEvent(QEvent.MouseButtonDblClick, pos, QPointF(flat.viewport().mapToGlobal(pos.toPoint())),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(flat.viewport(), ev)
    assert flat.transform().m11() == pytest.approx(k0 * nav.DOUBLE_CLICK_ZOOM, rel=1e-3)


def test_markers_keep_their_screen_size_while_zooming(flat):
    from routemap.gui.mapview import MarkerItem
    marker = flat.markers[0]

    def on_screen():
        return marker.deviceTransform(flat.viewportTransform()).mapRect(marker.boundingRect()).size()
    size0 = on_screen()
    flat.zoom(3)
    assert isinstance(marker, MarkerItem) and on_screen() == size0


def test_selecting_a_row_centres_its_marker_without_resetting_the_zoom(flat):
    flat.zoom(5)
    k = flat.transform().m11()
    hop = flat.markers[-1].hops[0]
    flat.highlight([hop], center=True)
    assert flat.transform().m11() == pytest.approx(k)
    marker = next(m for m in flat.markers if hop in m.hops)
    assert marker.selected
    centre = flat.viewport().rect().center()
    pos = flat.mapFromScene(marker.pos())
    assert abs(pos.x() - centre.x()) < 3 and abs(pos.y() - centre.y()) < 3


def test_the_world_cannot_be_dragged_off_screen(flat):
    world_top, world_bottom = -90 * nav.SCENE_UNITS_PER_DEG, 90 * nav.SCENE_UNITS_PER_DEG
    flat.zoom(4)
    for dy in (5000, -5000):
        for _ in range(40):
            flat.pan(0, dy)
        seen = flat.mapToScene(flat.viewport().rect()).boundingRect()
        assert seen.top() >= world_top - 1 and seen.bottom() <= world_bottom + 1
    for _ in range(200):
        flat.pan(5000, 0)                # sideways the world repeats; land is still in view
    seen = flat.mapToScene(flat.viewport().rect()).boundingRect()
    assert flat.sceneRect().contains(seen.center())
    flat.zoom(1e-6)                      # at the floor the whole world is in view
    seen = flat.mapToScene(flat.viewport().rect()).boundingRect()
    assert seen.top() <= world_top + 1 and seen.bottom() >= world_bottom - 1 or \
        seen.width() >= 360 * nav.SCENE_UNITS_PER_DEG - 1


# --------------------------------------------------------------- the globe ---

@pytest.fixture
def globe(app):
    from routemap.gui.globeview import GlobeView
    view = GlobeView()
    view.resize(900, 600)
    view.show()
    view.set_route(_route(), "heise.de")
    app.processEvents()
    return view


def test_globe_wheel_and_pinch_scale_trackpad_scroll_rotates(globe):
    z0, c0 = globe.zoom_, globe.center
    _wheel(globe, QPointF(450, 300), angle=(0, 120))
    assert globe.zoom_ == pytest.approx(z0 * nav.WHEEL_ZOOM_PER_NOTCH)
    _pinch(globe, QPointF(450, 300), 0.2)
    assert globe.zoom_ == pytest.approx(z0 * nav.WHEEL_ZOOM_PER_NOTCH * 1.2)
    z1 = globe.zoom_
    _wheel(globe, QPointF(450, 300), angle=(0, 40), pixel=(60, 0), phase=Qt.ScrollUpdate)
    assert globe.zoom_ == z1 and globe.center != c0


def test_globe_keys_and_reset(globe):
    globe.fit_route()
    z_fit, c_fit = globe.zoom_, globe.center
    QApplication.sendEvent(globe, QKeyEvent(QEvent.KeyPress, Qt.Key_Minus, Qt.NoModifier, "-"))
    QApplication.sendEvent(globe, QKeyEvent(QEvent.KeyPress, Qt.Key_Left, Qt.NoModifier))
    assert globe.zoom_ < z_fit and globe.center != c_fit
    QApplication.sendEvent(globe, QKeyEvent(QEvent.KeyPress, Qt.Key_0, Qt.NoModifier, "0"))
    assert globe.zoom_ == pytest.approx(z_fit) and globe.center == pytest.approx(c_fit)
