# The engine

`routemap.engine` is pure Python (httpx and dnspython, no Qt). FalconEye's Route
Map tab and the desktop app both use it.

## Front door

```python
from routemap.engine import analyse, analyse_sync, OFFLINE, default_sources

route = analyse_sync(trace_text, origin=(14.6, 121.0))            # live sources
route = analyse_sync(trace_text, origin=None, sources=OFFLINE)     # contacts nothing
route.to_dict()                                                    # see route.schema.json
```

`analyse(trace, origin, *, sources=None, progress=None) -> Route` is the async
form. `trace` is tracert, traceroute or mtr text, a `ParsedTrace`, or a list of
`Hop`. `progress(source, state, detail)` is told when each source (`reverse-dns`,
`hoiho`, `ip-db`) starts and finishes, times out, fails, or is off.

## Sources

`default_sources(user_agent=..., cache=..., use_hoiho=..., use_ip_db=...,
use_ptr=...)` builds the live set. Each source runs under its own hard time
budget and a source that runs out contributes nothing; it never fails the
trace. The carrier site-code table is offline and always consulted. Order:
Hoiho, site code, IP database; every candidate must pass the RTT bound.

| Source | Sends | To |
|---|---|---|
| PTR | public hop addresses with no name | the system resolver |
| Hoiho | public router hostnames | api.hoiho.caida.org |
| IP database | public hop addresses | stat.ripe.net |

Caches: `NullCache` (default), `MemoryCache`, `SqliteCache(path)`, or any object
with `get(key)` and `set(key, value)`.

## Running a trace

```python
from routemap.engine import run_trace, TraceOptions

result = run_trace("heise.de", TraceOptions(tool="auto", on_line=print, timeout=180))
result.text, result.argv, result.tool, result.cancelled, result.timed_out
```

An argument list, never a shell; the target must pass `validate_target`
(hostname or IP only). `cancel` is a `threading.Event`.

## Other modules

- `whereami.locate_me()`: this machine's public IP, placed at city level.
- `atlas.Atlas(key)`: probe selection, one-off traceroute, result as trace text.
- `cities.search()`, `cities.nearest()`: the bundled GeoNames list.
- `sitegen`: rebuilds the site-code table from carriers' published lists.
