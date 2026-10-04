"""
The bundled world maps, decoded. Qt-free, so it is testable without a display.

Built by routemap/gui/naturalearth.py from Natural Earth (public domain):
1:50m for the whole world and the globe, 1:10m with populated places for a
zoomed-in flat map. The 10m file is read the first time it is needed.
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


@functools.lru_cache(maxsize=2)
def _load(scale: str) -> dict:
    blob = resources.files("routemap.gui").joinpath(f"data/world_{scale}.json.gz").read_bytes()
    return json.loads(gzip.decompress(blob))


@functools.lru_cache(maxsize=2)
def world(scale: str = "50m") -> dict:
    """{"land": [[(lon, lat), ...], ...], "lakes": [...], "borders": [...], "source": str}"""
    body = _load(scale)
    quant = body["quant"]
    return {
        "source": body["source"],
        "land": [_decode(r, quant) for r in body["land"]],
        "lakes": [_decode(r, quant) for r in body["lakes"]],
        "borders": [_decode(r, quant) for r in body["borders"]],
    }


@functools.lru_cache(maxsize=1)
def places() -> list[dict]:
    """Natural Earth populated places, largest first:
    [{"name", "cc", "lat", "lon", "min_zoom", "pop"}]."""
    return [{"name": n, "cc": cc, "lat": lat, "lon": lon, "min_zoom": z, "pop": pop}
            for n, cc, lat, lon, z, pop in _load("10m").get("places", [])]
