"""
Route lines as the packets flew them: great-circle arcs, coloured by how much
RTT each step added. Qt-free, so the flat map, the globe and the tests share
one answer.

A straight line on an equirectangular map between Manila and Frankfurt runs
through the Indian Ocean; the shortest path runs over Central Asia. Each
segment is sampled along its great circle every few degrees; longitudes are
kept continuous (no jump at 180 degrees), so the flat map can draw the arc
across the antimeridian onto its repeated land.
"""
from __future__ import annotations

import math

from routemap_engine import osint

STEP_DEG = 2.0


def _vec(lat: float, lon: float) -> tuple[float, float, float]:
    la, lo = math.radians(lat), math.radians(lon)
    return (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))


def great_circle(lat1: float, lon1: float, lat2: float, lon2: float,
                 step_deg: float = STEP_DEG) -> list[tuple[float, float]]:
    """Points from (lat1, lon1) to (lat2, lon2) along the great circle, with
    longitudes continuous from *lon1* (they may leave [-180, 180])."""
    a, b = _vec(lat1, lon1), _vec(lat2, lon2)
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))
    omega = math.acos(dot)
    if omega < 1e-9:
        return [(lat1, lon1), (lat2, lon2)]
    n = max(1, math.ceil(math.degrees(omega) / step_deg))
    sin_o = math.sin(omega)
    out = []
    prev_lon = lon1
    for i in range(n + 1):
        t = i / n
        if abs(math.pi - omega) < 1e-6:
            # Antipodal: any great circle will do; go via the pole-ward midpoint.
            s1, s2 = math.cos(t * math.pi), math.sin(t * math.pi)
            v = (a[0] * s1, a[1] * s1, a[2] * s1 + s2)
        else:
            k1, k2 = math.sin((1 - t) * omega) / sin_o, math.sin(t * omega) / sin_o
            v = tuple(k1 * x + k2 * y for x, y in zip(a, b))
        lat = math.degrees(math.atan2(v[2], math.hypot(v[0], v[1])))
        lon = math.degrees(math.atan2(v[1], v[0]))
        while lon - prev_lon > 180:
            lon -= 360
        while lon - prev_lon < -180:
            lon += 360
        out.append((lat, lon))
        prev_lon = lon
    out[0] = (lat1, lon1)
    return out


def midpoint(points: list[tuple[float, float]]) -> tuple[float, float]:
    """The spherical centre of *points* (lat, lon), for centring the globe."""
    if not points:
        return (0.0, 0.0)
    x = y = z = 0.0
    for lat, lon in points:
        vx, vy, vz = _vec(lat, lon)
        x, y, z = x + vx, y + vy, z + vz
    if math.hypot(x, y, z) < 1e-9:
        return points[0]
    return (math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x)))


def segment_steps(groups: list[dict], origin: dict | None,
                  quiet_ms: float = osint.QUIET_MS, hot_ms: float = osint.HOT_MS) -> list[dict]:
    """One entry per drawn segment of the map's groups (mapview.route_groups),
    in order: {"to": index of the group the segment ends at, "step_ms",
    "class", "intensity"}.

    The step is the group's lowest RTT minus the RTT where the previous segment
    ended (0 at the origin). A group with no RTT has an unknown step, and the
    next step is measured from the last group that had one.
    """
    last = 0.0 if origin and origin.get("lat") is not None else None
    out = []
    for i, group in enumerate(groups):
        if group.get("silent"):
            continue
        rtts = [h["min_rtt_ms"] for h in group["hops"] if h.get("min_rtt_ms") is not None]
        rtt = min(rtts) if rtts else None
        step = (rtt - last) if (rtt is not None and last is not None) else None
        out.append({"to": i, "step_ms": step, "class": osint.classify_step(step, quiet_ms, hot_ms),
                    "intensity": osint.step_intensity(step, quiet_ms, hot_ms)})
        if rtt is not None:
            last = rtt
    return out
