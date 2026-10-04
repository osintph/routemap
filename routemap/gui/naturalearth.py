"""
Build the bundled world maps from Natural Earth vectors.

    python -m routemap.gui.naturalearth SRC_DIR                 # 1:50m
    python -m routemap.gui.naturalearth SRC_DIR --scale 10m     # 1:10m and places

SRC_DIR holds the GeoJSON files from Natural Earth's own repository at a
release tag (v5.1.2 for the shipped copies):

    https://github.com/nvkelso/natural-earth-vector/tree/v5.1.2/geojson
      ne_{50m,10m}_land.geojson
      ne_{50m,10m}_lakes.geojson
      ne_{50m,10m}_admin_0_boundary_lines_land.geojson
      ne_10m_populated_places_simple.geojson     (10m only: the city labels)

Two scales because they do different jobs. 1:50m draws the whole world and the
globe while it is dragged, where a finer coastline is below a pixel and costs
frame rate. 1:10m takes over when the flat map is zoomed in to a region, and
carries the populated places with Natural Earth's own ``min_zoom``, so a label
appears at the zoom its cartographers chose for it.

Natural Earth is public domain ("No permission is needed to use Natural Earth.
Crediting the authors is unnecessary."); the app credits it anyway.

WHAT THE BUILD DOES
-------------------
Each ring and line is simplified with Douglas-Peucker at TOLERANCE_DEG, then
quantised to 1/QUANT degrees and delta-encoded, which is what gets a 3 MB source
to the size of a small icon set. At the zoom a whole route needs, a 0.02 degree
tolerance (about 2 km) is below one pixel; zoomed right in on a city the
coastline gets visibly smoother, which is honest for a map whose markers are
only ever city-level claims.

The output is plain JSON (gzipped): no shapefile reader, no GDAL, nothing to
install, and the loader in routemap/gui/geometry.py is a dozen lines.
"""
from __future__ import annotations

import argparse
import gzip
import json
import pathlib
import sys

DATA = pathlib.Path(__file__).resolve().parent / "data"
SOURCE_TAG = "v5.1.2"
# scale: (tolerance in degrees, quantisation steps per degree, output file)
SCALES = {
    "50m": (0.02, 100, DATA / "world_50m.json.gz"),     # 0.01 degree steps
    "10m": (0.004, 500, DATA / "world_10m.json.gz"),    # 0.002 degree steps, about 200 m
}
TOLERANCE_DEG, QUANT, DEFAULT_OUT = SCALES["50m"]


def _perp(p, a, b) -> float:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    return abs(dy * x - dx * y + x2 * y1 - y2 * x1) / (dx * dx + dy * dy) ** 0.5


def simplify(points: list, tol: float) -> list:
    """Iterative Douglas-Peucker; keeps the endpoints."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        best, index = 0.0, None
        for i in range(start + 1, end):
            d = _perp(points[i], points[start], points[end])
            if d > best:
                best, index = d, i
        if index is not None and best > tol:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))
    return [p for p, k in zip(points, keep) if k]


def _encode(points: list, quant: int = QUANT) -> list[int]:
    """Quantise and delta-encode to a flat int list: x0, y0, dx1, dy1, ..."""
    out, px, py = [], 0, 0
    for lon, lat in points:
        x, y = round(lon * quant), round(lat * quant)
        if out and x == px and y == py:
            continue
        out += [x - px, y - py]
        px, py = x, y
    return out


def _rings(geometry: dict, polygons: bool) -> list:
    kind, coords = geometry["type"], geometry["coordinates"]
    if polygons:
        polys = [coords] if kind == "Polygon" else coords
        return [ring for poly in polys for ring in poly]
    return [coords] if kind == "LineString" else coords


def _layer(path: pathlib.Path, polygons: bool, min_points: int,
           tolerance: float = TOLERANCE_DEG, quant: int = QUANT) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for feature in data["features"]:
        for ring in _rings(feature["geometry"], polygons):
            simple = simplify([tuple(p[:2]) for p in ring], tolerance)
            if len(simple) >= min_points:
                out.append(_encode(simple, quant))
    return out


def _places(path: pathlib.Path) -> list:
    """[name, cc, lat, lon, min_zoom, population], largest first."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for feature in data["features"]:
        p = feature["properties"]
        name = p.get("nameascii") or p.get("name")
        if not name:
            continue
        rows.append([name, p.get("iso_a2") or "", round(float(p["latitude"]), 3),
                     round(float(p["longitude"]), 3), round(float(p.get("min_zoom") or 10), 1),
                     int(p.get("pop_max") or 0)])
    rows.sort(key=lambda r: (-r[5], r[0]))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the bundled Natural Earth world map.")
    parser.add_argument("src", type=pathlib.Path)
    parser.add_argument("--scale", choices=sorted(SCALES), default="50m")
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args(argv)
    tolerance, quant, default_out = SCALES[args.scale]
    args.out = args.out or default_out
    sc = args.scale

    body = {
        "source": f"Natural Earth 1:{sc} {SOURCE_TAG} (public domain), naturalearthdata.com",
        "quant": quant,
        "tolerance_deg": tolerance,
        "land": _layer(args.src / f"ne_{sc}_land.geojson", True, 4, tolerance, quant),
        "lakes": _layer(args.src / f"ne_{sc}_lakes.geojson", True, 4, tolerance, quant),
        "borders": _layer(args.src / f"ne_{sc}_admin_0_boundary_lines_land.geojson", False, 2,
                          tolerance, quant),
    }
    if sc == "10m":
        body["places"] = _places(args.src / "ne_10m_populated_places_simple.geojson")
    raw = json.dumps(body, separators=(",", ":")).encode()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 so rebuilding from the same source gives a byte-identical file.
    args.out.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    points = sum(len(r) // 2 for k in ("land", "lakes", "borders") for r in body[k])
    print(f"{len(body['land'])} land rings, {len(body['lakes'])} lakes, "
          f"{len(body['borders'])} borders, {points} points, "
          f"{args.out.stat().st_size} bytes -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
