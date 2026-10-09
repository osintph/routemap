# Privacy

Route Map runs on your machine. It has no account, no telemetry and no
automatic update check. Nothing is sent anywhere until you run or open a trace.

## What leaves this machine

| What | To | When |
|---|---|---|
| Public router hostnames from the trace | CAIDA Hoiho, api.hoiho.caida.org | each trace, unless Hoiho is off in Settings; answers are cached locally for 30 days |
| Public hop IP addresses the offline DB-IP Lite City file does not place (all of them while it is not installed) | RIPEstat, stat.ripe.net | each trace, unless the IP database is off |
| Public hop IP addresses, their routed prefixes and AS numbers, for route details (prefix, RPKI, RIS paths and visibility, BGP updates, AS overview) | RIPEstat, stat.ripe.net | after each trace; abuse contact and RIR only when you open a hop's details |
| The two countries and the public name of a RIPE Atlas anchor, for a typical latency between them | RIPE Atlas, atlas.ripe.net | after each trace; public data, no key, no credits |
| Your RIPE Atlas key and the target, to list your own earlier measurements | RIPE Atlas, atlas.ripe.net | only when you choose Compare with an Earlier Atlas Measurement |
| A download request for DB-IP Lite City and ASN | DB-IP, download.db-ip.com | only when you choose Download on first run, Settings > Update now, or `routemap data update` |
| PTR (reverse DNS) queries for public hops with no name | your own DNS resolver | each trace, unless reverse DNS is off |
| Your public IP address, to find your city | RIPEstat, stat.ripe.net | at startup, only while no origin is set in Settings |
| Your RIPE Atlas API key, your network's AS number (or your country code if no probe is on your network), and the target | RIPE Atlas, atlas.ripe.net | only when Atlas is on in Settings with your own key and you choose Trace from a RIPE Atlas Probe. RIPE NCC publishes every measurement, target included |
| Your public IP address, to find your network's AS number for the Atlas probe | RIPEstat, stat.ripe.net | only for an Atlas trace |
| A request for the latest release tag | GitHub, api.github.com | only when you choose Check for Updates or run `routemap --check-update` |
| A download of the release file for your system, `SHA256SUMS` and `SHA256SUMS.ed25519` | GitHub, github.com and its release-asset host release-assets.githubusercontent.com | only when you choose Download and check after Check for Updates. Not counted by the project site |

**Continuous mode** (Watch) sends the same ICMP echo probes as a trace, to the
target and the routers on the way, once per hop per cycle and at most 30 a
second, until you stop it or it reaches its time limit. The lookups above run
once for the hops of the first cycle and then only for a hop or router not
seen before, never every cycle. It never uses RIPE Atlas.

**Settings > Sources > Online lookups** switches every row above except the
trace itself, the explicit update check and downloads you start: off, nothing
new leaves this machine, and hops are placed from the offline data (carrier
site codes, DB-IP Lite City and ASN) only.

Private, CGNAT and reserved addresses (your own network and your ISP's carrier
NAT) are never looked up anywhere. Your origin coordinates are never sent to
anyone, RIPE Atlas included: they only rank Atlas probes on your machine.

Every request to these services identifies the app in its User-Agent
(`routemap/<version> (+https://github.com/osintph/routemap; traceroute geolocation)`), and RIPEstat
requests also carry `sourceapp=routemap-desktop`. The project runs no server
of its own that the app talks to.

When this list changes, this file and Help > Privacy change with it.
Questions: support@getroutemap.app.

## What stays on this machine

In the config folder (macOS `~/Library/Application Support/routemap/`, Windows
`%APPDATA%\routemap\`, Linux `~/.config/routemap/`):

- `settings.json`: your settings, including the origin and your RIPE Atlas key
  if you entered one (readable only by your user where the OS allows).
- `cache.sqlite3`: Hoiho answers for router hostnames, and `ipgeo-cache.sqlite3`:
  IP database answers for public hop addresses, each kept 30 days by default.
  Clear both in Settings or with `routemap cache clear`.
- `history.json`: the last 50 traces, only while history is on. Clear it in
  Settings or the History panel.
- `site_codes.tsv`: only after `routemap sites update`.
- `ripe-cache.sqlite3`: RIPEstat route details and Atlas baselines, each kept
  for its own short lifetime (30 minutes for BGP updates, up to 30 days for
  registration data). `routemap cache clear` and Settings clear it too.
- `data/`: DB-IP Lite City (when you download or import it) and DB-IP Lite
  ASN (unpacked from the app on first use). No trace data is written there.

Comparisons are made from routes already on this machine (the current trace,
an export you choose, or your own Atlas measurements); nothing is stored for
them. Exports are written only to the file you choose.
