# GUI data

## `world_50m.json.gz`

The offline world map: land, lakes and country boundary lines from
[Natural Earth](https://www.naturalearthdata.com/) 1:50m, release tag
**v5.1.2** of <https://github.com/nvkelso/natural-earth-vector>.

**Licence: public domain.** From Natural Earth's terms: "All versions of Natural
Earth raster + vector map data found on this website are in the public domain."
Crediting is not required; the app credits it on the map and in exports anyway.

Built by `python -m routemap.gui.naturalearth SRC_DIR`, where SRC_DIR holds
`ne_50m_land.geojson`, `ne_50m_lakes.geojson` and
`ne_50m_admin_0_boundary_lines_land.geojson` from that tag. Douglas-Peucker at
0.02 degrees, quantised to 0.01 degrees, delta-encoded, gzipped: about 114 KB
for 1,393 land rings, 463 lakes and 393 boundary lines. The build is
deterministic, so rebuilding from the same tag gives the same bytes.
