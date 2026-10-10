# Route Map user guide

## Install

Download the latest release from
[GitHub Releases](https://github.com/osintph/routemap/releases).

- **Windows 10/11 (x86_64)**: run `routemap-<version>-windows-x86_64-setup.exe`.
  Choose **Install for me only** (no administrator rights, installed in your
  user folder) or **Install for all users** (always Program Files). Route Map is then in the Start
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
- **Linux x86_64**: `sudo apt install ./routemap-<version>-linux-x86_64.deb`
  (Debian, Ubuntu and relatives) or `sudo dnf install
  ./routemap-<version>-linux-x86_64.rpm` (Fedora, RHEL; `zypper install` on
  openSUSE). Route Map is then in the applications menu and `routemap` on the
  PATH. Without installing: `chmod +x` the `.AppImage` and run it, or unpack the
  `.tar.gz` and run `./routemap`. Where the distribution does not allow
  unprivileged ICMP, traces use `traceroute`, which then has to be installed.

**Upgrade** by installing the new version over the old one (installer,
package or DMG); settings, history and databases stay. **Help > Check for
Updates** says whether a newer version is out and offers the file for your
system. **Download and check** fetches it from this project's GitHub releases
into a folder only you can read and checks three things before anything runs:
that `SHA256SUMS.ed25519` is a signature by the update key built into this
version over the release tag and `SHA256SUMS`, that `SHA256SUMS` lists the
file once, and that the file's SHA-256 matches. Then it runs the installer
(Windows), opens the disk image (macOS), opens the `.deb` or `.rpm` in your
software installer, or replaces a running AppImage in place and restarts. A
failed check deletes the download and says which check failed. These downloads
go to GitHub directly, so they do not appear in the project site's download
statistics. Versions up to 0.2.0-beta.5 open the download in the browser
instead. **Uninstall**: Settings > Apps on Windows, the Trash on macOS,
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

On the first start a short tour points at the origin, the target field, the
map, the hop table and the menus; **Skip tour** or Esc ends it, the arrow keys
move through it, and **Help > Show the Tour** brings it back. Settings is
**Route Map > Settings** on macOS and **Edit > Settings** on Windows and Linux.

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

Loss at a hop counts as ICMP rate limiting when any later hop that answered
shows less of it: the packets were getting through, and the router only
declined to answer some probes. Its **Loss** cell is greyed. The route summary,
the PDF and the JSON export (`"loss"`) report only the loss measured at the
destination; when the destination never answers, its loss is reported as
unknown, never as 0%.

### The map

Lines follow the great circle between hops, the way the packets actually fly,
and are coloured by how much round-trip time each step added: grey under 15 ms,
warming to the hot colour at 60 ms (both set in **Settings > Map**). A dashed
line crosses hops that did not answer or a country-only placement.

**Settings > Map > Colours** has a **Colour-blind safe** option: rust to navy
on the light map and yellow to vermilion on the dark one, chosen with a
colour-vision simulation so that the three steps stay apart for protan,
deutan and tritan colour vision, each at least 3:1 against the map. Hot steps
are also drawn dash-dot, so colour is never the only cue. The exports use the
same colours.

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
| Arrow keys | previous or next hop | previous or next hop |
| `Home` and `End` | first hop, destination | first hop, destination |
| `Enter`, `Esc` | select the hop's rows, clear | select the hop's rows, clear |
| `Shift` + arrow keys | pan | turn |
| `0`, or the **Fit** button | frame the route | centre on the route |

Tab moves between the target field, the map, the summary and the hop table;
the arrow keys move between hops in the map and in the table, and each follows
the other. Every control has a name for screen readers, and a hop is read out
as its number, place, network, RTT, loss and notes.

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

## Paths

**Paths** (next to Trace), **Trace > Find All Paths** (Ctrl+Shift+T) or
`routemap TARGET --paths` finds the paths a load balancer can send your packets
along, each with its own loss and latency. Many networks spread traffic over
several equal routes; an ordinary trace shows one of them, or a mix of them
hop by hop.

How it works: Paris traceroute keeps every probe of one *flow* on one path (the
fields routers hash stay the same while the probe's sequence number changes),
and different flows can take different paths. At each hop Route Map adds flows
until the multipath detection algorithm's stopping rule says, with 95%
confidence, that no next hop is left unseen: 9 flows when a hop has one
router, 17 when it has two, and so on. Each path found is then pinged ten
times with one of its own flows, for its own latency and loss to the target.

What you see: the routes where the paths part ways drawn one colour per path,
with the path's letter; a **Paths** column in the hop table and a sub-row for
each router at a hop where the paths differ (3a, 3b); and the **Paths** list
under the table with each path's share of the flows, where it differs, and its
RTT and loss to the target. Choose a path in the list to show it alone on the
map.

"At least": some load balancers do not spread ICMP probes, so a path can stay
hidden; the count is a lower bound. A router that sends every packet another
way (per-packet balancing) is named, and does not make paths of its own.

**Limits**, so it never floods a network: at most 20 probes a second (the
default rate of CAIDA's scamper), at most 1,500 probes per discovery, the pings
included (Settings > Trace can lower this), at most 64 flows, and it stops
after 3 silent hops. A typical discovery takes 20 to 60 seconds. Paths uses the
built-in ICMP prober without administrator rights on macOS and Linux; Windows
is not supported yet (Windows' own ICMP function picks each probe's identifier
and sequence number itself, so it cannot keep a flow on one path).

## Continuous mode

**Watch** (next to Trace), **Trace > Watch Continuously** (Ctrl+Shift+W) or
`routemap --watch TARGET` probes one target again and again, mtr style: every
hop once per cycle, with the built-in ICMP prober and no administrator rights.
The hop table switches to the mtr columns: Loss, Sent, Last, Avg, Best, Worst
and StDev (the standard deviation of the answered RTTs, the jitter). The map is
drawn from the first full cycle; later cycles only add hops that were not there
before, so nothing is looked up again every second.

Under the table, the **ping plot** shows the selected hop (solid line) and the
destination (dashed) over the last 5 minutes; the keys 1 to 4 choose 5 minutes,
15 minutes, an hour or the whole session. Lost probes are marks on the baseline,
and a path change is a vertical rule with its cycle. The plot follows the row or
marker you select and the RTT palette you chose in Settings.

**Path changes** are listed with their cycle and time: a hop answering from a
different router, a hop starting or stopping to answer, the destination moving
to another hop count. A hop's routers are compared over the last 10 cycles with
the 10 before, so a load balancer alternating between the same routers is never
reported as a change.

**Loss** follows the same rule as a single trace: loss at a hop that later hops
do not share is ICMP rate limiting, greyed with its note; only the loss at the
destination is real. If the computer sleeps or the app is suspended, the missed
time is a gap in the plot and the statistics, never loss, and the session notes
it.

**Pause** (P, when the cursor is not in a text field), **Stop** (Ctrl+.) and
**Reset counters** (a button and a Trace menu item, with no shortcut) control a
running session. A stopped session stays on screen: export it as PDF (the table,
the changes, the gaps and one plot per hop for the whole session) or JSON
(format version 4, with the statistics, the plot data and the changes), compare
it with another run as with any trace, or reopen it from History or File >
Open Trace.

**Limits**, in Settings > Live, so it never floods a network. They follow mtr:

| | Default | Allowed | Where it comes from |
|---|---|---|---|
| Interval | 1 s | 1 to 60 s | mtr's default, and the shortest it allows without root |
| Probes per second | at most 30 | fixed | what mtr sends by default on a 30-hop path |
| Wait for a reply | 1 s | fixed | as a single trace and mtr |
| Silent hops probed | 5 past the last answer | fixed | mtr's `--max-unknown` default in its manual |
| Session length | 1 hour | 5 minutes to 8 hours | a limit of Route Map's own |

Stopped sessions are kept in History, 50 MB of them at most together; past that
the oldest sessions are dropped first. Continuous mode runs over IPv4 or IPv6,
as Settings > Trace > IP version chooses, and never uses RIPE Atlas.

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
- **Trace** also has **IP version**: Automatic (the address your system
  prefers), IPv4 only or IPv6 only, for a host that has both; it applies to
  traces, Paths and continuous mode. And the **Paths** probe budget (1,500 at
  most).
- **RIPE Atlas**: the API key and the Trace menu entry, and **Reverse traces**
  with **Withdraw consent**; see below.
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

1. Create a key at [atlas.ripe.net/keys](https://atlas.ripe.net/keys/) with the
   *schedule a new measurement* permission, and *credits read* if you want your
   balance shown before each trace.
2. In **Settings > RIPE Atlas**, paste it and switch on the Trace menu entry.
3. Choose **Trace > Trace from a RIPE Atlas Probe**. The first time, confirm
   that the measurement will be public. Every time, the dialog shows your
   balance, what this trace costs and what is left after it. A key RIPE does
   not accept stops the trace there, with a button to Settings; a key without
   *credits read* hides the balance but can still trace.

Route Map finds a connected probe on your network's AS (or, failing that, in
your country), schedules one traceroute (60 credits: RIPE charges a one-off
measurement twice what a periodic one costs), and draws the result from the
probe's location. **Atlas measurements are public**: RIPE NCC publishes
every measurement, including the target. Your origin coordinates are never
sent; they only rank probes on your machine.

## Reverse trace

The route from you to a target is often not the route back. **Reverse trace**
(next to the summary once a trace is on screen, or **Trace > Reverse Trace via
RIPE Atlas**) asks a RIPE Atlas probe near the target to trace back to you, and
shows both directions side by side.

- The probe is a connected one in the target's network (its AS), or failing
  that in its country, nearest the target, and never one in your own network.
  If there is none, nothing is scheduled and no credits are spent.
- **It publishes your public IP address.** Atlas measurements are public, and
  a reverse trace's target is your public IP. Before the first one Route Map
  says so and asks you to agree; nothing runs without that. Every time, it
  shows the probe, the IP address that will be published (it changes when you
  change networks) and the cost, 60 credits. **Settings > RIPE Atlas >
  Withdraw consent** stops reverse traces at once until you agree again.
- The result is drawn dashed in its own colour, with diamonds where the two
  directions split and rejoin, and listed under the table aligned by network,
  not by hop number, with the rows that differ tinted. Different routes each
  way are normal on the Internet.
- It is kept in History and in the JSON export with the trace it reverses,
  and the PDF has a Reverse trace section. From the command line:
  `routemap TARGET --reverse --publish-my-ip` (the second option is the
  agreement, given for that run only).

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

**Help > Create Bug Report** makes a zip with what helps most and nothing
private by default: `about.txt` (Route Map and engine version and commit, OS,
Python, Qt, kind of build) and `settings.json` with every key and token
replaced by `(removed)`, and your set origin (city or coordinates) and a
FalconEye address other than the public one removed too. Tick **Include the
last trace** to add the trace on screen as `last-trace.json` (target, every hop
and your origin; the origin then stays in `settings.json` as well). The dialog
shows every file exactly as it will be saved. Route Map sends nothing: you
attach the zip yourself.

See also: [troubleshooting](troubleshooting.md), [known limitations](limitations.md),
[questions](faq.md).
