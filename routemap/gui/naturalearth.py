"""
Build the bundled world map from Natural Earth 1:50m vectors.

    python -m routemap.gui.naturalearth SRC_DIR [--out routemap/gui/data/world_50m.json.gz]

SRC_DIR holds the three GeoJSON files from Natural Earth's own repository at a
release tag (v5.1.2 for the shipped copy):

    https://github.com/nvkelso/natural-earth-vector/tree/v5.1.2/geojson
      ne_50m_land.geojson
      ne_50m_lakes.geojson
      ne_50m_admin_0_boundary_lines_land.geojson

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

TOLERANCE_DEG = 0.02
QUANT = 100  # 0.01 degree steps
DEFAULT_OUT = pathlib.Path(__file__).resolve().parent / "data" / "world_50m.json.gz"
SOURCE_TAG = "v5.1.2"


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


def _encode(points: list) -> list[int]:
    """Quantise and delta-encode to a flat int list: x0, y0, dx1, dy1, ..."""
    out, px, py = [], 0, 0
    for lon, lat in points:
        x, y = round(lon * QUANT), round(lat * QUANT)
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


def _layer(path: pathlib.Path, polygons: bool, min_points: int) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for feature in data["features"]:
        for ring in _rings(feature["geometry"], polygons):
            simple = simplify([tuple(p[:2]) for p in ring], TOLERANCE_DEG)
            if len(simple) >= min_points:
                out.append(_encode(simple))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the bundled Natural Earth world map.")
    parser.add_argument("src", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    body = {
        "source": f"Natural Earth 1:50m {SOURCE_TAG} (public domain), naturalearthdata.com",
        "quant": QUANT,
        "tolerance_deg": TOLERANCE_DEG,
        "land": _layer(args.src / "ne_50m_land.geojson", True, 4),
        "lakes": _layer(args.src / "ne_50m_lakes.geojson", True, 4),
        "borders": _layer(args.src / "ne_50m_admin_0_boundary_lines_land.geojson", False, 2),
    }
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
