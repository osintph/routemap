# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
uses [Semantic Versioning](https://semver.org/).

## [0.2.0-beta.2] - 2026-10-05

### Added

- **Installers.** Windows: one installer for a per-user install (no
  administrator rights) or a per-machine one (Program Files), with a Start menu
  entry, an uninstaller in Settings > Apps and an optional PATH entry for
  `routemap-cli.exe`; installing a new version over an old one upgrades it.
  Linux: `.deb` and `.rpm` packages with a menu entry. Every release builds
  them from the same commit as the DMGs, the AppImage and the zip, and installs,
  checks and removes each one on clean Windows, Ubuntu, Debian and Fedora
  systems before anything is published.
- **Check for Updates offers the file for your system**: the Windows
  installer, the DMG for your Mac's processor, or the `.deb`, `.rpm` or
  AppImage on Linux, with a Download button that opens it in your browser.

### Changed

- **The same trace on every platform.** Traces now probe with the engine's own
  ICMP prober on Windows, macOS and Linux: 30 hops, three probes per hop, one
  second per reply, and every router that answers a hop is listed. Windows
  `tracert` showed one router per hop and macOS and Linux `traceroute` used
  UDP probes that many destinations ignore, so the same target looked
  different on each. No administrator rights are needed. On a Linux system
  that does not allow unprivileged ICMP (`net.ipv4.ping_group_range`), traces
  fall back to `traceroute` with UDP and Settings > Trace says why. The system
  tools remain as options (UDP, and TCP where you have administrator rights).
- **One look on every platform:** the same style, palette, accent colour and
  font (IBM Plex Sans, bundled, SIL Open Font Licence) on Windows, macOS and
  Linux; only the window frame and the menu bar position differ.
- **Theme:** System (default), Light or Dark, in Settings > Map and View >
  Theme; applies to the window, the map and the exports, and is remembered.
- **Nothing disappears without a reason.** When RIPEstat or RIPE Atlas does not
  answer, the route summary says so and why (for example "RIPEstat did not
  answer within 20 s") instead of leaving a section out. The slow RIPEstat
  lookups (RIS paths, BGP updates, visibility) now wait up to 20 s and retry
  once. With no origin set, the RTT chart says why there is no physics floor.
- **City labels at every zoom**, the largest places first, so whether a map
  shows any no longer depends on the window size.
- **Help > About and `--version` show the commit** the build was made from, and
  every release checks that all platforms were built from the same commit and
  render the same panels, legends, charts and table.
- **Help > About and `--version` also show the engine's commit** whenever the
  app is built on an engine commit rather than a published release.
- **Version spelling**: the version reads `0.2.0-beta.2` everywhere you see it
  (About, `--version`, file names, installer, Settings > Apps, packages), the
  same as the release tag; earlier releases' files used `0.2.0b1`.
- Requires routemap-engine 0.4.0.

### Fixed

- **Windows: round trip times keep their decimals.** Every probe is timed with
  the same high-resolution clock on every platform; on Windows, hops beyond the
  access network used to read as whole milliseconds.
- **The built-in prober is named as such** ("Built-in ICMP prober"), not "Unix
  traceroute", from the first line of a trace.
- **Disagreeing RIS paths are explained**: the BGP view says where they leave
  the trace's path and through which AS, also when some paths agree.
- **The BGP updates chart marks the hours RIPEstat has no data for yet**
  (hatched, with the time its data reaches) instead of drawing them as quiet.
- **The Hoiho ruleset date is always shown**, also when the answers came from
  the cache.
- **One RPKI term**: a prefix without a ROA is "not found" in the hop table,
  the PDF, the AS path and the BGP view alike (the table said "no ROA").

## [0.2.0-beta.1] - 2026-10-04

### Added

- **Globe.** Flat or globe (View > Globe, Ctrl+G, or Settings > Map). The
  globe is centred on the route and turns when dragged.
- **Great-circle lines coloured by RTT step**: grey under 15 ms, warming to
  the hot colour at 60 ms, both thresholds in Settings > Map. Dashed across
  silent hops and country-only placements. A legend says which is which.
- **Replay** (Ctrl+R) draws the route again hop by hop.
- **Finer map when zoomed in**: Natural Earth 1:10m coastlines and borders,
  and city labels from Natural Earth's own zoom levels.
- **Route summary** beside the table: AS path with RPKI badges, countries
  transited with your sensitive countries flagged, a likely-anycast note, a
  typical latency for the trip from RIPE Atlas anchors, what RIPE RIS peers see
  for the destination prefix (path agreement, visibility), and the last 48
  hours of BGP updates for it.
- **RTT sparkline** against the lowest RTT each placement allows.
- **Hop details**: AS, routed prefix, RIR, RPKI, abuse contact with Copy, AS
  overview, and **Open in FalconEye** (IP Reputation, address on the
  clipboard; also on the table's right-click menu).
- **ASN and RPKI columns** in the hop table.
- **Compare two runs**: Trace Again and Compare, Compare with an Export, and
  Compare with an Earlier Atlas Measurement (your own, no credits). Hops are
  matched by place; the PDF and JSON include the comparison.
- **Offline IP databases**: DB-IP Lite ASN ships with the app; DB-IP Lite City
  is offered on first run (about 60 MB), or imported from a file on a machine
  with no internet, and updated from Settings or `routemap data update`.
  While City is not installed, IP database placements come from RIPEstat and
  the Source column says so. IP Geolocation by DB-IP, CC BY 4.0.
- **One Online lookups switch** (Settings > Sources): off, nothing new leaves
  the machine.
- Command line: `routemap data update|import|status`, `--compare FILE`; PDF
  and `--envelope` JSON carry the route summary.

### Fixed

- **Map navigation.** A trackpad pinch did nothing (macOS sends it as a native
  gesture, which no part of the map handled); two-finger scroll crept the zoom
  instead of panning; and after Fit on a long route the wheel could not zoom
  out, because the zoom floor sat at about the fit's own scale. Now the wheel
  zooms around the pointer, pinch zooms around the fingers, two-finger scroll
  pans (turns the globe), double-click zooms in, `+`, `-`, arrows and `0`
  work after clicking the map, and zoom stops at the whole world and at
  city-street level.

### Changed

- An IP database placement between two hops in one area is rejected when the
  RTT did not rise enough for the detour (engine 0.3.0). It showed on the
  sample: DB-IP put heise's hop 12 in Chicago between two Frankfurt hops.
- JSON export format version 2 (adds `insight`, `attributions` and
  `comparison`; version 1 files still open). Its `schema` link now points at
  the engine repository, where the schema lives.
- PRIVACY.md and Help > Privacy list the new lookups: RIPEstat route details,
  RIPE Atlas anchor baselines, DB-IP downloads.
- Engine: routemap-engine 0.3.0 from PyPI.

### Not in this release

- **Submarine cables**: TeleGeography's cable data is sold under licence (only
  its map images are CC BY-SA), so there is no cable overlay.
- **Internet exchange points**: PeeringDB's terms do not allow bundling its
  prefix list; permission is being asked and the code is switched off
  until then.

## [0.1.0-beta.5] - 2026-10-04

### Changed

- **Help > Support Route Map** lists the ways to support the project, in
  order: Ko-fi, PayPal, Bitcoin and Monero, with the addresses selectable and
  copyable. It opens only when you choose it. GitHub Sponsors is gone.
- **Contact**: support@getroutemap.app, in Help > About and Help > Privacy.
- The bundled sample trace no longer shows the maintainer's home network: the
  router, LAN, carrier-NAT and first ISP hops carry documentation addresses
  (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24).
- Settings: the cache line now covers both caches, Hoiho and the IP
  database, and counts both.
- The engine comes from PyPI (routemap-engine 0.2.1, the same code as
  before).
- Documentation: a fuller user guide (exports, paste mode, settings, RIPE
  Atlas), troubleshooting, known limitations and a FAQ. Corrected: `mtr --json`
  output was never supported; `mtr --report` is.

## [0.1.0-beta.4] - 2026-10-04

### Changed

- **Route Map is free and open source** under the GNU AGPL-3.0, and its
  repository is public. Contributions are welcome under a Contributor Licence
  Agreement (CLA.md, CONTRIBUTING.md). No licence key is needed.
- **Releases are on GitHub Releases**, with a GPG-signed `SHA256SUMS`.
- **Windows: a zip instead of a single exe.** Extract it and run `routemap.exe`
  in the `Route Map` folder; `routemap-cli.exe` is beside it. beta.3's
  one-file exe, which unpacked itself at start, was deleted by Microsoft
  Defender on download as a false positive. Both exes now carry full version
  information and an application manifest, no packer is used, and every
  Windows build is scanned with Defender before release. The Windows build is
  still unsigned.
- Help > Support Route Map opens the project's sponsor page (nothing else, and
  never on its own). Help > About links the project site.
- Help > Privacy and PRIVACY.md now spell out everything an Atlas trace sends.

## [0.1.0-beta.3] - 2026-10-03

### Fixed

- Hops at the end of a trace that answered but could not be placed were
  labelled "No reply". They are now "not placed", and the legend says
  "Not placed (yet)" while a trace is running.
- `routemap-cli.exe` on Windows wrote redirected output (to a file or a pipe)
  in the ANSI code page, so separators and accented city names came out as
  replacement characters. Redirected output is now UTF-8.

### Changed

- RIPEstat answers are cached on this computer for the same 30 days as Hoiho
  answers (`ipgeo-cache.sqlite3`), so a route traced again does not ask
  RIPEstat again. "Clear cache" clears both.
- RIPEstat requests identify the app with `sourceapp=routemap-desktop`
  (routemap-engine 0.2.1).

## [0.1.0-beta.2] - 2026-10-03

Fixes from beta 1 on real Windows 11 hardware, and a compiled build.

### Changed since beta.1

- **Windows: no console.** `routemap.exe` is now a windowed program: it never
  opens a console or Windows Terminal tab, and closing a terminal it was started
  from no longer closes the app. The command line is a separate
  `routemap-cli.exe`.
- **Hops appear as the trace runs.** Each hop is placed on the map and added to
  the table the moment its line arrives (hostname first, the usual sources, the
  RTT bound); hops that do not answer show at once as a dashed "no reply"
  marker. When the tool finishes, only ECMP cleanup and the annotations are
  added. The map keeps fitting the hops so far until you zoom or pan; **Fit**
  hands it back.
- **Nothing covers the map while tracing.** The tracing card is gone; state is
  in the status bar, with a small indicator next to Stop.
- **Right panel.** The hop table is on top and grows live; the tool's raw
  output is in a collapsible panel below it, collapsed by default (View > Tool
  Output).
- **Selection follows both ways.** Click a marker to select its rows (all of
  them for a collapsed marker such as "14-15"); click a row, or move with the
  arrow keys, to highlight and centre its marker. Esc clears.
- **Country-only placements are marked.** A hop the IP database could place
  only to a country (for example `apa.customers.nextlayer.net`, "AT") is drawn
  as a hollow marker labelled "AT (country only)", shows "ip-db, country only"
  in the Source column, and no longer stretches Fit.
- **Marker hover** shows the same fields as the table row: hop, location,
  hostname, IP, RTT, loss, source and notes.
- **Compiled build.** The app is compiled with Nuitka on every platform.
- Help > Third-Party Notices lists every bundled component with its licence.
- Beta builds were handed to testers through a download site with a login for
  each tester, with a GPG-signed `SHA256SUMS`.

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
