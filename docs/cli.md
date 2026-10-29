# Command-line reference

On Windows the command is `routemap-cli.exe` (in the `Route Map` folder); on
macOS `"/Applications/Route Map.app/Contents/MacOS/routemap-app"`; on Linux the
AppImage or `./routemap`. Examples below say `routemap`.

```
routemap                                 open the window
routemap TARGET                          open the window with the trace started
routemap TARGET --json                   trace here, print the route model, exit
routemap TARGET --png map.png --pdf r.pdf
routemap TARGET --origin "Manila, PH"    or --origin 14.6,121.0
routemap parse FILE [--json|--png|--pdf] analyse a trace run elsewhere
routemap sites update [--dry-run]        refresh the carrier site-code table
routemap cache clear                     forget cached Hoiho, IP database and RIPE answers
routemap data update                     download this month's DB-IP Lite City and ASN
routemap data import FILE                install a DB-IP Lite City .mmdb or .mmdb.gz
routemap data status                     which offline databases are installed
routemap --check-update                  ask GitHub for the latest release tag
routemap --version
```

## Options

| Option | Meaning |
|---|---|
| `--json` | print the route model as JSON on stdout |
| `--envelope` | with `--json`: the full export (trace text, tool, flags) around the route |
| `--png FILE` | write the map as a 1600x900 PNG |
| `--pdf FILE` | write the PDF report |
| `--origin ORIGIN` | where the trace starts: `"lat,lon"` or a city such as `"Manila, PH"`; overrides Settings for this run |
| `--offline` | contact nothing: offline data only (carrier site codes, DB-IP Lite City and ASN) |
| `--compare FILE` | compare with an earlier JSON export: the PDF gets a comparison section, `--envelope` JSON a `comparison` block |
| `--watch` | trace TARGET continuously, mtr style, printing a live table; Ctrl+C stops |
| `--interval SECONDS` | with `--watch`: seconds per cycle, 1 to 60 (default from Settings > Live, 1) |
| `--count N` | with `--watch`: stop after N cycles |
| `--duration TIME` | with `--watch`: stop after this long, as `90s`, `10m` or `2h`, 5 minutes to 8 hours (default 1 hour) |
| `--paths` | find the paths a load balancer spreads your traffic over; some may stay hidden (ICMP Paris, or TCP Paris to port 443 on Windows; at most 20 probes a second and the Settings budget, 1,500 at most; stops after 5 silent hops, then asks the target at full TTL); prints the resolved address, why discovery ended, the hops with the paths through each and one line per path, or exports with `--json`, `--png`, `--pdf` |
| `--reverse` | also trace back from a RIPE Atlas probe near the target to your public IP (Atlas key from Settings; 60 credits) |
| `--publish-my-ip` | with `--reverse`: agree, for this run, that your public IP address is published as the target of a public RIPE Atlas measurement. Without it `--reverse` refuses (exit code 2) |
| `-4`, `-6` | trace (or `--paths`, `--watch`) over IPv4 only or IPv6 only, for this run |
| `--dns` | time the target's DNS lookup (system resolver and the resolvers in Settings > Probes) and print it; with `--json`, `--png` or `--pdf` it is in the export |
| `--resolver ADDR` | also time the lookup through this resolver (an IP address), this run only; repeatable |
| `--no-dns` | do not time DNS lookups this run (the target is still resolved once) |
| `--ports [LIST]` | test TCP ports on the target, one connection attempt each: the list given (`443,80,22`) or the one in Settings; at most 32, no ranges. Put it after the target. With `--paths`, the port test is printed after the paths |
| `--from AGENT` | run the trace (or `--paths`, `--ports`) on a remote agent from Settings > Agents, over your own ssh, one connection; not with `--watch` or `--reverse` |

With `--watch`, `--json` prints the export (format version 5, with the
session) on stdout when the session ends, and the table goes to stderr. On a
terminal the table redraws in place; piped, it prints once at the end. Under
the table are the notes: path changes, gaps (sleep or suspend, not counted),
clock changes (cycles kept) and, when sleep and a change of the system clock
could not be told apart, "Clock check off" with the reason. In the session,
`gaps` lists each gap (`from`, `to`, `seconds`), `clock_steps` each change of
the system clock whose cycle was kept (`at`, and `seconds`, negative when the
clock was set back), and `clock_fallback` is null or the reason the clock
check was off. Values
outside the limits are refused with the reason; the limits are those of
Settings > Live (see the [guide](guide.md#continuous-mode)).

The PDF and the `--envelope` JSON include the route summary: the AS path and
countries always (offline), and the RIPE details unless `--offline` is given
or Online lookups are off in Settings.

`TARGET` is a hostname or an IP address. `parse FILE` reads the output of
`traceroute`, `tracert` or `mtr --report` saved to a file. (A Route Map JSON
export is reopened in the window with File > Open Trace.)

Progress and the trace tool's own output go to stderr, so `--json` output on
stdout can be piped. Nothing is written anywhere except the files named on the
command line and, as in the window, the cache and history in the config folder.
Redirected output is UTF-8 on every platform.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | the trace tool printed nothing, or the trace could not be parsed |
| 2 | invalid target, unreadable file or wrong arguments |
| 3 | no trace tool found (install `traceroute`, or `mtr`) |

## Examples

```bash
# Trace and keep everything
routemap example.com --json --envelope > example.json --png example.png

# Map a traceroute someone sent you, from their city
routemap parse their-trace.txt --origin "Frankfurt, DE" --pdf report.pdf

# No network at all: placements from carrier site codes and DB-IP Lite only
routemap parse trace.txt --offline --json

# DNS timing through your resolver and Quad9, and three ports
routemap example.com --dns --resolver 9.9.9.9 --ports 443,80,22

# Paths from a server in Settings > Agents
routemap example.com --from fra-vps --paths
```
