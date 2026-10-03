# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0-beta.1] - 2026-10-03

The first desktop build, for trying on real machines. Not code-signed yet.

### Added

- The desktop app on macOS (Apple silicon and Intel), Windows and Linux: trace
  from this machine with the system's own tracert, traceroute or mtr, with the
  tool's output streaming into the window, then the route on an offline world
  map and in a sortable, copyable hop table, with unplaced hops and their reasons.
- Paste or open a trace run elsewhere; open a JSON export again.
- Exports: a 1600 x 900 PNG of the whole route with legend and provenance; a PDF
  report with the facts of the trace, the map, the hop table, unplaced hops, how
  locations were decided and the raw trace as an appendix; the JSON route model
  with the trace text, tool and flags.
- Origin from the public IP (city level, labelled approximate), or set in
  Settings by city search (offline), coordinates or a click on the map.
- Settings for the trace tool and flags (probe types that need administrator
  rights are flagged, never escalated), each network source, the Hoiho cache
  lifetime, RIPE Atlas and history. Everything is kept in one config folder.
- Optional RIPE Atlas traces with your own key, after a one-time
  acknowledgement that Atlas measurements are public.
- History of the last 50 traces, off by a setting.
- The command line: `routemap TARGET` with `--json`, `--png`, `--pdf` and
  `--origin`; `routemap parse`, `routemap sites update`, `routemap cache clear`,
  `routemap --check-update`.
- Builds: a .dmg per Mac architecture (ad-hoc signed so it runs on Apple
  silicon), a Windows .exe, a Linux AppImage and .tar.gz, each smoke-tested in
  CI by opening the window offscreen, loading a trace and exporting all three
  formats.

### Earlier, toward this beta

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
