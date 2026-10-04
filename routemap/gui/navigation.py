"""
How the maps respond to wheels, trackpads and keys, as plain functions.

Why this exists (0.2.0): the flat map turned every wheel event into zoom, so
a Mac trackpad's two-finger scroll crept the zoom instead of panning; a pinch
(a native zoom gesture on macOS) had no handler at all and went nowhere; and
the zoom-out floor sat at about the scale of a world-wide route's fit, so the
wheel did nothing outward after Fit. The decisions now live here, Qt-free and
tested, and both the flat map and the globe use them.

Devices, as Qt reports them:
  - mouse wheel: angle steps of 120 per notch, no pixel delta (or a pixel
    delta from a mouse driver that smooths scrolling): zoom.
  - macOS trackpad two-finger scroll: pixel deltas, phased: pan.
  - macOS trackpad pinch: a native zoom gesture: zoom (handled by the views).
  - Windows precision touchpad: two-finger scroll arrives as small angle
    steps (zoom, like a wheel); pinch arrives as Ctrl+wheel (zoom).
  - Ctrl (Cmd on macOS) + wheel: always zoom.
"""
from __future__ import annotations

import math

SCENE_UNITS_PER_DEG = 4.0      # mapview.SCALE
MAX_WEB_ZOOM = 12.0            # about 35 m per pixel: city streets, not buildings
WHEEL_ZOOM_PER_NOTCH = 1.25
BUTTON_ZOOM = 1.4
KEY_PAN_PX = 90
DOUBLE_CLICK_ZOOM = 2.0
FIT_PAD = 0.12                 # fraction of the route's extent added around it
MIN_FIT_SPAN_DEG = 6.0         # a one-city route is framed no tighter than this


def max_scale() -> float:
    """The largest view scale (view pixels per scene unit)."""
    px_per_deg = 256.0 * 2 ** MAX_WEB_ZOOM / 360.0
    return px_per_deg / SCENE_UNITS_PER_DEG


def min_scale(view_w: float, view_h: float) -> float:
    """The smallest view scale: the whole world in view. Below this there is
    nothing more to see, only an ever smaller map."""
    if view_w <= 0 or view_h <= 0:
        return 1e-3
    return min(view_w / (360.0 * SCENE_UNITS_PER_DEG), view_h / (180.0 * SCENE_UNITS_PER_DEG))


def clamp_scale(scale: float, view_w: float, view_h: float) -> float:
    return max(min_scale(view_w, view_h), min(scale, max_scale()))


def zoom_factor(current: float, factor: float, view_w: float, view_h: float) -> float:
    """The factor actually applied so the result stays within the limits."""
    if current <= 0:
        return 1.0
    return clamp_scale(current * factor, view_w, view_h) / current


def fit_scale(span_w: float, span_h: float, view_w: float, view_h: float) -> float:
    """The scale that frames a route of *span_w* by *span_h* scene units in the
    view, with padding, never tighter than MIN_FIT_SPAN_DEG and within the
    limits."""
    floor = MIN_FIT_SPAN_DEG * SCENE_UNITS_PER_DEG
    w = max(span_w, floor) * (1 + 2 * FIT_PAD)
    h = max(span_h, floor) * (1 + 2 * FIT_PAD)
    if view_w <= 0 or view_h <= 0:
        return 1.0
    return clamp_scale(min(view_w / w, view_h / h), view_w, view_h)


def wheel_action(angle_x: int, angle_y: int, pixel_x: int, pixel_y: int, *,
                 zoom_modifier: bool, touchpad: bool) -> tuple:
    """("zoom", factor) or ("pan", dx, dy) in view pixels, or ("none",).

    A trackpad's scroll pans; a wheel zooms; Ctrl/Cmd + either zooms (Windows
    and Chrome send a touchpad pinch as Ctrl+wheel).
    """
    if zoom_modifier:
        steps = (angle_y or pixel_y / 4.0) / 120.0
        return ("zoom", WHEEL_ZOOM_PER_NOTCH ** steps) if steps else ("none",)
    if touchpad and (pixel_x or pixel_y):
        return ("pan", pixel_x, pixel_y)
    if touchpad and (angle_x or angle_y) and not (pixel_x or pixel_y):
        # A touchpad without pixel deltas (some Windows drivers) still scrolls.
        return ("pan", angle_x / 2.0, angle_y / 2.0)
    steps = angle_y / 120.0
    if steps:
        return ("zoom", WHEEL_ZOOM_PER_NOTCH ** steps)
    if angle_x:
        return ("pan", angle_x / 2.0, 0)
    return ("none",)


def gesture_factor(value: float) -> float:
    """A native zoom gesture's value is the change in scale this event (0.05 =
    5 % bigger); never let one event flip or collapse the map."""
    return max(0.5, min(2.0, 1.0 + value))


def web_zoom(scale: float) -> float:
    return math.log2(max(1e-9, scale * SCENE_UNITS_PER_DEG * 360.0 / 256.0))
