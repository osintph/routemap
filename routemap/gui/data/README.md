# GUI data

## `world_50m.json.gz` and `world_10m.json.gz`

The offline world maps: land, lakes and country boundary lines from
[Natural Earth](https://www.naturalearthdata.com/) 1:50m and 1:10m, release tag
**v5.1.2** of <https://github.com/nvkelso/natural-earth-vector>. The 10m file
also carries Natural Earth's populated places (name, country, position,
`min_zoom`, population) for the city labels.

**Licence: public domain.** From Natural Earth's terms: "All versions of Natural
Earth raster + vector map data found on this website are in the public domain."
Crediting is not required; the app credits it on the map and in exports anyway.

Built by `python -m routemap.gui.naturalearth SRC_DIR [--scale 10m]`, where
SRC_DIR holds `ne_{50m,10m}_land.geojson`, `ne_{50m,10m}_lakes.geojson`,
`ne_{50m,10m}_admin_0_boundary_lines_land.geojson` and (10m)
`ne_10m_populated_places_simple.geojson` from that tag.

- 50m: Douglas-Peucker at 0.02 degrees, quantised to 0.01 degrees: about 114 KB
  for 1,393 land rings, 463 lakes and 393 boundary lines.
- 10m: 0.004 degrees, quantised to 0.002 degrees: about 966 KB for 5,992 land
  rings, 1,555 lakes, 7,980 boundary lines and 7,342 places.

Both are delta-encoded and gzipped with mtime 0, so a rebuild from the same tag
gives the same bytes.
