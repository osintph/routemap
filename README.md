# routemap

Hostname-first, physics-checked traceroute maps.

Drawing a traceroute by feeding each hop to an IP geolocation database produces
a path that crosses oceans it never crossed, because a backbone router's address
is registered wherever its operator filed the prefix, not where the router is.
routemap reads the router's own hostname first (CAIDA Hoiho, then a carrier
site-code table built from each carrier's published router list), falls back to
the IP database only after that, and checks every candidate location against the
speed of light: a place the measured round trip could not have reached is
rejected, whichever source claimed it.

This repository holds the engine that powers the Route Map tab in
[FalconEye](https://github.com/osintph/falconeye), and the native desktop app
for Linux, macOS and Windows being built on it. The desktop app runs the trace
on your own machine, so the map starts where you are.

**Status:** the engine is extracted and in use by FalconEye. The desktop app is
in development; there is no installer yet.

## The engine

```python
from routemap.engine import analyse_sync, run_trace, TraceOptions

result = run_trace("heise.de", TraceOptions(on_line=print))   # system traceroute
route = analyse_sync(result.text, origin=(14.6, 121.0))
route.to_dict()   # the route model; schema in routemap/engine/route.schema.json
```

See [docs/engine.md](docs/engine.md) for the API, the sources and what each one
is sent.

```bash
pip install git+https://github.com/osintph/routemap
routemap parse trace.txt --origin Manila           # route model as JSON
routemap parse trace.txt --origin 14.6,121.0 --offline
```

## Credits

- [CAIDA Hoiho](https://api.hoiho.caida.org/) router hostname geolocation.
- [RIPE NCC](https://stat.ripe.net/) RIPEstat, for IP geolocation.
- [GeoNames](https://www.geonames.org/) city list (cities15000), used under
  [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).
- Arelion's public looking glass, for the carrier's own router site list.

## Licence

GNU Affero General Public License v3.0. See [LICENSE](LICENSE).
