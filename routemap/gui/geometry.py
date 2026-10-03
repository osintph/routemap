"""
The bundled world map, decoded. Qt-free, so it is testable without a display.

Built by routemap/gui/naturalearth.py from Natural Earth 1:50m (public domain).
"""
from __future__ import annotations

import functools
import gzip
import json
from importlib import resources

ATTRIBUTION = "Map data: Natural Earth (public domain)"


def _decode(flat: list[int], quant: int) -> list[tuple[float, float]]:
    points, x, y = [], 0, 0
    for i in range(0, len(flat), 2):
        x += flat[i]
        y += flat[i + 1]
        points.append((x / quant, y / quant))
    return points


@functools.lru_cache(maxsize=1)
def world() -> dict:
    """{"land": [[(lon, lat), ...], ...], "lakes": [...], "borders": [...], "source": str}"""
    blob = resources.files("routemap.gui").joinpath("data/world_50m.json.gz").read_bytes()
    body = json.loads(gzip.decompress(blob))
    quant = body["quant"]
    return {
        "source": body["source"],
        "land": [_decode(r, quant) for r in body["land"]],
        "lakes": [_decode(r, quant) for r in body["lakes"]],
        "borders": [_decode(r, quant) for r in body["borders"]],
    }
