# Privacy

Route Map runs on your machine. It has no account, no telemetry and no
automatic update check. Nothing is sent anywhere until you run or open a trace.

## What leaves this machine

| What | To | When |
|---|---|---|
| Public router hostnames from the trace | CAIDA Hoiho, api.hoiho.caida.org | each trace, unless Hoiho is off in Settings; answers are cached locally for 30 days |
| Public hop IP addresses | RIPEstat, stat.ripe.net | each trace, unless the IP database is off |
| PTR (reverse DNS) queries for public hops with no name | your own DNS resolver | each trace, unless reverse DNS is off |
| Your public IP address, to find your city | RIPEstat, stat.ripe.net | at startup, only while no origin is set in Settings |
| Your RIPE Atlas API key, your network's AS number (or your country code if no probe is on your network), and the target | RIPE Atlas, atlas.ripe.net | only when Atlas is on in Settings with your own key and you choose Trace from a RIPE Atlas Probe. RIPE NCC publishes every measurement, target included |
| Your public IP address, to find your network's AS number for the Atlas probe | RIPEstat, stat.ripe.net | only for an Atlas trace |
| A request for the latest release tag | GitHub, api.github.com | only when you choose Check for Updates or run `routemap --check-update` |

Private, CGNAT and reserved addresses (your own network and your ISP's carrier
NAT) are never looked up anywhere. Your origin coordinates are never sent to
anyone, RIPE Atlas included: they only rank Atlas probes on your machine.

Every request to these services identifies the app in its User-Agent
(`routemap/<version> (+https://github.com/osintph/routemap; traceroute geolocation)`), and RIPEstat
requests also carry `sourceapp=routemap-desktop`. The project runs no server
of its own that the app talks to.

When this list changes, this file and Help > Privacy change with it.

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

Exports are written only to the file you choose.
