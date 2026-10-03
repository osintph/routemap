# Route Map user guide

## Install

Download the latest release from
[GitHub Releases](https://github.com/osintph/routemap/releases).

- **Windows 10/11 (x86_64)**: download `routemap-<version>-windows-x86_64.zip`,
  extract it, and run `routemap.exe` in the `Route Map` folder. Keep the folder
  together; you can pin `routemap.exe` to Start or the taskbar. Until the build
  is code-signed, SmartScreen may say "Windows protected your PC": choose
  **More info**, then **Run anyway**. `routemap.exe` never opens a console;
  `routemap-cli.exe` beside it is the command line.
- **macOS 12+**: open the `.dmg` for your Mac (`macos-arm64` for Apple silicon,
  `macos-x86_64` for Intel) and drag Route Map to Applications. The app is not
  notarised, so the first start is blocked: right-click it, choose **Open**,
  then **Open** again (on macOS 15: System Settings > Privacy & Security >
  **Open Anyway**).
- **Linux x86_64**: `chmod +x` the `.AppImage` and run it, or unpack the
  `.tar.gz` and run `./routemap`. Tracing needs `traceroute` (for example
  `sudo apt install traceroute`); `mtr` is used if you choose it in Settings.

Check a download (optional): import the release key
([RELEASE-KEY.asc](../RELEASE-KEY.asc)) with `gpg --import RELEASE-KEY.asc`,
run `gpg --verify SHA256SUMS.asc SHA256SUMS`, then
`sha256sum -c SHA256SUMS --ignore-missing` (Linux),
`shasum -a 256 -c SHA256SUMS --ignore-missing` (macOS) or `Get-FileHash <file>`
(PowerShell). The release key is
`D57C 7E26 C19F 9436 E2D6 6F37 4080 97D1 91DD F981`.

## First trace

1. Type a hostname or IP address in the box at the top and press **Trace**.
2. Hops appear on the map and in the table as the trace runs. The tool's own
   output is under **Tool output** below the table (View > Tool Output).
3. When it finishes, the map fits the route. Zoom with the wheel or pinch, drag
   to pan, **Fit** to see the route again, **World** for the whole map.

Your starting point (the origin) comes from your public IP address until you
set one in **Settings > Origin**: a city, coordinates, or a point picked on the
map. A set origin is remembered, and while one is set the public-IP lookup
never happens.

## Reading the result

Every hop row says where its location came from, in the **Source** column, and
the marker has the same colour:

| Source | Meaning |
|---|---|
| `hoiho` | The router's hostname matched one of CAIDA Hoiho's rules for that operator, and the rule names the city. |
| `site-code` | The hostname contains a carrier's own site code (for example `ffm` for Frankfurt on Arelion's network), from the bundled table. |
| `ip-db` | Neither hostname source knew it, so the IP geolocation database (RIPEstat) placed it. Treat it as a hint: backbone addresses often geolocate to where the prefix was registered. |
| `ip-db, country only` | The database knew only the country. The marker is hollow, sits in the country, and the map does not zoom out for it. |
| `local` | Your own network or your ISP's carrier NAT. Never looked up anywhere. |
| `unresolved` | Not placed: it did not answer, or no source placed it within the physics bound. The **Unplaced** panel says why. |

Every placement, whatever its source, is checked against the round-trip time.
Light in fibre covers about 100 km per millisecond of round trip, so a hop
answering in 5 ms cannot be more than about 500 km away (plus a small allowance
for the origin being approximate). A placement farther than that is rejected
and the row's **Notes** say so.

Hops in the same city in a row collapse into one marker (for example `14-15`).
Click a marker to select its rows; click a row, or use the arrow keys, to
highlight its marker. Esc clears. Hover a marker to see its row's fields.

The **Notes** column also flags what the trace itself shows: a hop that answers
only some probes because the router rate-limits ICMP (not real loss further
on), a destination that does not answer ICMP, and RTTs that jump in a way that
suggests the reply took a different path back.

## Paste a trace

**File > Paste Trace** (Ctrl+Shift+V) takes the output of `traceroute`,
`tracert` or `mtr --report` run anywhere: another machine, a
looking glass, a colleague's email. The dialog detects the format as you paste
and asks where the trace was run from, because the origin anchors every
physics check. **File > Open Trace** does the same for a saved file or a Route
Map JSON export.

## Exports

**File > Export** (Ctrl+E):

- **PNG**: the map with the legend, 1600 by 900, light or dark (**Dark map**).
- **PDF**: the map, the hop table, the sources used, the unplaced hops and,
  if **Include the raw trace text** is on, the tool's output.
- **JSON**: everything, including the trace text, to open again later or to
  process elsewhere.

Exports are written only to the file you choose. The command line exports the
same three formats; see the [command-line reference](cli.md).

## Settings

- **Origin**: from your public IP address (one lookup, only while nothing else
  is set), a city, coordinates, or a point picked on the map.
- **Trace**: the tool (detected at startup: `tracert` on Windows, `traceroute`
  on macOS and Linux, or `mtr` if installed), its flags, and **Give up after**,
  the time limit for one trace.
- **Sources**: switch each source on or off: CAIDA Hoiho, the bundled carrier
  site-code table (offline), the IP geolocation database, and reverse DNS for
  hops without a name. **Keep Hoiho and IP database answers for** sets the
  local cache lifetime (30 days by default); **Clear cache** empties both.
- **RIPE Atlas**: the API key and the Trace menu entry; see below.
- **Privacy**: the trace history (the last 50 traces, on by default, clearable).

## RIPE Atlas mode

With a RIPE Atlas account you can trace from an Atlas probe on your own network
instead of from this computer, which helps when your machine cannot run a trace
(a locked-down laptop) or when you want a second vantage point.

1. Create a key at [atlas.ripe.net/keys](https://atlas.ripe.net/keys/) with only
   the *schedule a new measurement* permission.
2. In **Settings > RIPE Atlas**, paste it and switch on the Trace menu entry.
3. Choose **Trace > Trace from a RIPE Atlas Probe**. The first time, confirm
   that the measurement will be public.

Route Map finds a connected probe on your network's AS (or, failing that, in
your country), schedules one traceroute (30 credits), and draws the result from
the probe's location. **Atlas measurements are public**: RIPE NCC publishes
every measurement, including the target. Your origin coordinates are never
sent; they only rank probes on your machine.

## Privacy

Nothing is sent anywhere until you run or open a trace, and then only what
[PRIVACY.md](../PRIVACY.md) lists (also Help > Privacy). Each source can be
switched off in Settings; with all of them off, placements come only from the
bundled carrier site codes.

## Reporting a problem

Please [open an issue on GitHub](https://github.com/osintph/routemap/issues).
If you would rather not use GitHub, email support@getroutemap.app. What helps
most: your OS and version, the Route Map version (Help > About), what you
traced, what you expected, and a screenshot or a JSON export (File > Export).
A JSON export contains the trace, so leave it out if the path is private.

See also: [troubleshooting](troubleshooting.md), [known limitations](limitations.md),
[questions](faq.md).
