# Route Map user guide

## Install

Download the latest release from
[GitHub Releases](https://github.com/osintph/routemap/releases).

- **Windows 10/11 (x86_64)**: run `routemap-<version>-windows-x86_64-setup.exe`.
  Choose **Install for me only** (no administrator rights, installed in your
  user folder) or **Install for all users** (Program Files). Route Map is then in the Start
  menu and in Settings > Apps; tick **Add routemap-cli.exe to PATH** to use the
  command line in any terminal. `routemap.exe` never opens a console;
  `routemap-cli.exe` beside it is the command line. Until the build is
  code-signed, SmartScreen may say "Windows protected your PC": choose
  **More info**, then **Run anyway**. Without installing: extract
  `routemap-<version>-windows-x86_64.zip` and run `routemap.exe` in the
  `Route Map` folder.
- **macOS 12+**: open the `.dmg` for your Mac (`macos-arm64` for Apple silicon,
  `macos-x86_64` for Intel) and drag Route Map to Applications. The app is not
  notarised, so the first start is blocked: right-click it, choose **Open**,
  then **Open** again (on macOS 15: System Settings > Privacy & Security >
  **Open Anyway**).
- **Linux x86_64**: `sudo apt install ./routemap_<version>-<build>_amd64.deb`
  (Debian, Ubuntu and relatives) or `sudo dnf install
  ./routemap-<version>-<build>.x86_64.rpm` (Fedora, RHEL; `zypper install` on
  openSUSE). Route Map is then in the applications menu and `routemap` on the
  PATH. Without installing: `chmod +x` the `.AppImage` and run it, or unpack the
  `.tar.gz` and run `./routemap`. Where the distribution does not allow
  unprivileged ICMP, traces use `traceroute`, which then has to be installed.

**Upgrade** by installing the new version over the old one (installer,
package or DMG); settings, history and databases stay. **Help > Check for
Updates** says whether a newer version is out and offers the file for your
system. **Uninstall**: Settings > Apps on Windows, the Trash on macOS,
`sudo apt remove routemap` or `sudo dnf remove routemap` on Linux. Settings and
history are kept in `%APPDATA%\routemap`, `~/Library/Application
Support/routemap` or `~/.config/routemap` until you delete that folder.

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
| `ip-db (DB-IP)` | Neither hostname source knew it, so the offline DB-IP Lite City database on this machine placed it. Treat it as a hint: backbone addresses often geolocate to where the prefix was registered. |
| `ip-db (RIPEstat, online)` | The same, answered by RIPEstat online, because DB-IP Lite City is not installed or did not know the address. |
| `ip-db, country only` | The database knew only the country. The marker is hollow, sits in the country, and the map does not zoom out for it. |
| `local` | Your own network or your ISP's carrier NAT. Never looked up anywhere. |
| `unresolved` | Not placed: it did not answer, or no source placed it within the physics bound. The **Unplaced** panel says why. |

Every placement, whatever its source, is checked against the round-trip time.
Light in fibre covers about 100 km per millisecond of round trip, so a hop
answering in 5 ms cannot be more than about 500 km away (plus a small allowance
for the origin being approximate). A placement farther than that is rejected
and the row's **Notes** say so. A database placement between two hops in the
same area is also rejected when the RTT did not rise enough to pay for the
detour (a Frankfurt hop, then "Chicago", then Frankfurt again 46 ms later).

Hops in the same city in a row collapse into one marker (for example `14-15`).
Click a marker to select its rows; click a row, or use the arrow keys, to
highlight its marker. Esc clears. Hover a marker to see its row's fields.

The **Notes** column also flags what the trace itself shows: a hop that answers
only some probes because the router rate-limits ICMP (not real loss further
on), a destination that does not answer ICMP, and RTTs that jump in a way that
suggests the reply took a different path back.

### The map

Lines follow the great circle between hops, the way the packets actually fly,
and are coloured by how much round-trip time each step added: grey under 15 ms,
warming to the hot colour at 60 ms (both set in **Settings > Map**). A dashed
line crosses hops that did not answer or a country-only placement.

Traces probe the same way on every platform: ICMP echo from the app's own
prober, 30 hops, three probes per hop, one second per reply, with every
router that answers a hop listed (a hop answered by two routers shows both).
Settings > Trace offers the system `traceroute` for UDP probes, or TCP
probes with administrator rights.

**View > Theme** (or Settings > Map) sets System, Light or Dark for the
window, the map and the exports.

**Flat** and **Globe** switch projection (View > Globe, Ctrl+G); the globe is
centred on the route and turns when you drag it.

Moving around the map:

| | Flat map | Globe |
|---|---|---|
| Mouse wheel | zoom around the pointer | zoom |
| Trackpad pinch (or Ctrl + scroll) | zoom around the fingers | zoom |
| Trackpad two-finger scroll | pan | turn |
| Drag | pan | turn |
| Double-click | zoom in one step | zoom in one step |
| `+` and `-` (after clicking the map) | zoom | zoom |
| Arrow keys | pan | turn |
| `0`, or the **Fit** button | frame the route | centre on the route |

Zoom stops at the whole world and at city-street level, markers and labels
keep their size, and selecting a row centres its marker without changing the
zoom. Zoomed in on the flat map, the
coastline gets finer and city labels appear. **Replay** (Ctrl+R) draws the
route again hop by hop.

### The route summary

Above the hop table:

- **AS path**: the networks the trace crossed, from the bundled DB-IP Lite ASN
  database, with an RPKI badge per network (do the routes it announces have a
  valid ROA?).
- **Countries transited**, in order. Countries you list in **Settings > Map >
  Sensitive countries** are flagged.
- **Destination**: a "likely anycast" note when the destination answers too
  fast for where it is registered, or belongs to a large content network.
- **Typical latency (RIPE Atlas)**: what RIPE's anchors measure between the
  two countries today, against what you measured.
- **BGP view (RIPE RIS)**: how many of RIPE's route-collector peers see the
  destination prefix, and whether their AS paths match the one your packets
  took.
- **BGP updates, last 48 h**: routing activity for the destination prefix; a
  burst at trace time is called out.
- **RTT per hop and the physics floor**: measured RTT against the lowest RTT
  each placement allows.

The table gains **ASN** and **RPKI** columns. Select one hop for its details:
address, how it was placed, AS, routed prefix, RIR, RPKI, abuse contact (with
Copy) and an AS overview. **Open in FalconEye** (also on the right-click menu)
opens IP Reputation in FalconEye with the address on the clipboard.

Everything in the summary that comes from RIPE needs **Online lookups** on; a
source that does not answer shows "unavailable" and nothing else changes.

### Compare two runs

**Trace > Trace Again and Compare** (Ctrl+Shift+R) runs the same target again
and shows the earlier run faint and dashed under the new one, with changed
hops ringed, the table rows tinted, and a summary such as "Marseille and Paris
are gone (hops 8 to 9 then)". **Compare with an Export** compares the route on
screen with a JSON export, and **Compare with an Earlier Atlas Measurement**
with your own last RIPE Atlas traceroute to the target (no credits spent).
Hops are matched by place, not by hop number, and a run that simply stopped
answering is not reported as lost hops. The PDF includes the comparison.

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
- **PDF**: the map, the route summary (AS path, countries, RIPE data), the hop
  table with ASN and RPKI, any comparison, the unplaced hops and, if **Include
  the raw trace text** is on, the tool's output.
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
- **Sources**: **Online lookups** switches every online source at once; off,
  nothing new leaves the machine. Under it, each source on its own: CAIDA
  Hoiho, the bundled carrier site-code table (offline), the IP geolocation
  database (RIPEstat), and reverse DNS for hops without a name. **Keep Hoiho
  and IP database answers for** sets the local cache lifetime (30 days by
  default); **Clear cache** empties every cache. **Offline data** shows the
  DB-IP Lite months installed, with **Update now** (download this month's) and
  **Import database file** (for a machine with no internet).
- **Map**: projection, the two RTT step colour thresholds, sensitive
  countries, and the FalconEye address used by Open in FalconEye.
- **RIPE Atlas**: the API key and the Trace menu entry; see below.
- **Privacy**: the trace history (the last 50 traces, on by default, clearable).

## Offline data

The app ships with DB-IP Lite ASN (for the AS path). On first start it offers
DB-IP Lite City, about 60 MB, so IP database placements happen on your machine
instead of at RIPEstat: **Download**, **Import File** (copy
`dbip-city-lite-YYYY-MM.mmdb.gz` from https://db-ip.com/db/download/ip-to-city-lite
on another machine) or **Not Now**. Until it is installed, the Source column
says `ip-db (RIPEstat, online)`. Both files are updated monthly by DB-IP; use
**Settings > Sources > Update now** or `routemap data update`. Licence: CC BY
4.0, IP Geolocation by DB-IP.

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
