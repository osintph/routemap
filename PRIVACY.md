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
| The target, as a measurement request | RIPE Atlas, with your own key | only when you choose Trace from a RIPE Atlas Probe; such measurements are public |
| A request for the latest release tag | GitHub, api.github.com | only when you choose Check for Updates or run `routemap --check-update` |

Private, CGNAT and reserved addresses (your own network and your ISP's carrier
NAT) are never looked up anywhere. Your origin coordinates are never sent to
anyone, RIPE Atlas included.

## What stays on this machine

In the config folder (macOS `~/Library/Application Support/routemap/`, Windows
`%APPDATA%\routemap\`, Linux `~/.config/routemap/`):

- `settings.json`: your settings, including the origin and your RIPE Atlas key
  if you entered one (readable only by your user where the OS allows).
- `cache.sqlite3`: Hoiho answers for router hostnames. Clear it in Settings or
  with `routemap cache clear`.
- `history.json`: the last 50 traces, only while history is on. Clear it in
  Settings or the History panel.
- `site_codes.tsv`: only after `routemap sites update`.

Exports are written only to the file you choose.
