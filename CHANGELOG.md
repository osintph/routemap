# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

Work toward 0.1.0, the first desktop release.

### Added

- The Route Map engine, extracted from FalconEye v3.35.3 into
  `routemap.engine`: the tracert, traceroute and mtr parsers, PTR resolution,
  the CAIDA Hoiho client, the carrier site-code table and its generator, the
  bundled GeoNames city list, the RIPEstat IP geolocation fallback, the RTT
  physics bound, the hop annotations and ECMP handling. Behaviour is unchanged;
  FalconEye v3.36.0 runs its Route Map tab on this package.
- `analyse(trace_text | hops, origin) -> Route`, with every network source
  passed in as a `Sources` value rather than read from configuration, a
  per-source progress callback, and `geo.OFFLINE` for a run that contacts
  nothing.
- `Route.to_dict()` and its JSON Schema, `routemap/engine/route.schema.json`.
- `run_trace(target, options)`: runs the system tracert, traceroute or mtr
  with an argument list (never a shell), streams output line by line, and
  supports cancel and a timeout.
- Pluggable Hoiho answer caches: none, in memory, or one SQLite file.
- `routemap parse FILE` on the command line.
- The desktop window, as a static mockup for review: the offline Natural Earth
  1:50m world map (public domain, about 114 KB bundled), route markers that
  collapse same-city hops, unwrap across the antimeridian and move aside with
  a leader line when they would overlap, the sortable hop table, unplaced hops
  with reasons, live trace output, history, settings, export, paste and RIPE
  Atlas dialogs, light and dark. `python -m routemap.gui.mockup` renders every
  state from real recorded traces.

### Tagged

- `v0.1.0.dev1` (2026-10-03): the engine extraction FalconEye v3.36.0 pins.
