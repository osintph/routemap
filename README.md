# routemap

**Route Map** draws the path your packets take to a host, on a map, starting
where you are. It runs the traceroute on your own machine with your system's
own tool, places each router, and shows what it could not place and why.

Most traceroute maps feed each hop's IP address to a geolocation database and
draw whatever comes back. The result crosses oceans the packet never crossed,
because a backbone router's address is registered wherever its operator filed
the prefix, not where the router is: a Hong Kong router can come back as Paris.

Route Map reads the router's own hostname first. Carriers name their routers
after the site they are in (`hnk-b4-link.ip.twelve99.net` is Arelion in Hong
Kong), so the hostname is better evidence than the registry. It asks CAIDA's
Hoiho, which publishes per-carrier naming rules with measured accuracy, then a
site-code table built from each carrier's own published router list. The IP
database is the fallback only when neither knows the hostname.

Every candidate location is then checked against physics. Light in fibre
covers about 200 km per millisecond, so a hop that answered in 58 ms cannot be
more than about 5,800 km away (plus some slack for the origin being a city,
not a point). A location further than that is rejected whichever source
claimed it, and the hop either falls back to the next source or is listed as
unplaced with the reason. Loss that disappears at a later hop is labelled as
ICMP rate limiting, an RTT that drops at the next hop as an asymmetric return
path, and a silent tail as a destination that does not answer ICMP, so the
usual misreadings are called out on the map instead of left as surprises.

This repository is the engine behind the Route Map tab in
[FalconEye](https://github.com/osintph/falconeye) and the desktop app built on
it. Licence: AGPL-3.0.

## Install

**0.1.0-beta.1 is a beta and is not code-signed yet.** Downloads are on the
[releases page](https://github.com/osintph/routemap/releases). Each binary
carries its own Qt, so expect 60 to 110 MB.

| Platform | File | First run |
|---|---|---|
| macOS 12+ on Apple silicon | `routemap-...-macos-arm64.dmg` | drag to Applications; right-click, **Open**, **Open** |
| macOS 12+ on Intel | `routemap-...-macos-x86_64.dmg` | as above |
| Windows 10/11 x64 | `routemap-...-windows-x86_64.exe` | SmartScreen: **More info**, **Run anyway** |
| Linux x86_64 | `routemap-...-linux-x86_64.AppImage` | `chmod +x` and run |
| Linux x86_64 | `routemap-...-linux-x86_64.tar.gz` | unpack, run `./routemap` |
| Anywhere with Python 3.11+ | `pip install "routemap[gui] @ git+https://github.com/osintph/routemap@v0.1.0-beta.1"` in a virtualenv | `routemap` |

On macOS, if right-click Open is not offered, remove the download quarantine
once: `xattr -d com.apple.quarantine "/Applications/Route Map.app"`. Gatekeeper
warns because the app is not yet signed with an Apple Developer ID; that is
expected until a signed release.

Tracing needs the system's traceroute tool. Windows and macOS ship one. On
Linux: `sudo apt install traceroute` (Debian, Ubuntu), `sudo dnf install
traceroute` (Fedora) or `sudo pacman -S traceroute` (Arch); `mtr` is optional
and adds per-hop loss. The app never asks for administrator rights.

## Use

Type a hostname or IP address and press **Enter**. The tool's output streams
into the window as it runs; when it finishes, the hops are placed on the map and
in the table, with anything unplaced listed underneath with its reason.

- **File > Paste Trace** or **Open Trace**: analyse output of `tracert`,
  `traceroute` or `mtr --report` run on any machine.
- **File > Export** (Ctrl/Cmd+E): a 1600 x 900 PNG of the whole route, a PDF
  report (map, hop table, unplaced hops, tool and flags, raw trace), or the JSON
  route model ([schema](routemap/engine/route.schema.json)).
- **History**: the last 50 traces, in the View menu. Off in Settings if you
  prefer nothing stored.
- **Settings** (Ctrl/Cmd+,): origin, trace tool and flags, which sources are
  used, cache lifetime, RIPE Atlas, history.

From a terminal:

```bash
routemap heise.de                               # open the window and trace
routemap heise.de --json > route.json           # trace here, print the route model
routemap heise.de --png map.png --pdf report.pdf
routemap heise.de --origin "Manila, PH"         # or --origin 14.6,121.0
routemap parse trace.txt --pdf report.pdf       # a trace run elsewhere
routemap sites update                           # refresh the carrier site-code table
routemap cache clear
routemap --check-update                         # asks GitHub for the latest tag, nothing else
```

In the macOS app the command is `"/Applications/Route Map.app/Contents/MacOS/routemap"`.

### Origin

Every route starts at your machine. By default that is your public IP address
looked up to city level, shown as approximate, and wrong on a VPN or a Tor
exit. Set it yourself in **Settings > Origin**: search the bundled city list
(offline), type coordinates, or click the map. Once set, the public IP lookup
is skipped entirely. The origin is never a server's location.

### RIPE Atlas (optional)

With your own RIPE Atlas API key (Settings > RIPE Atlas), **Trace > Trace from a
RIPE Atlas Probe** runs the traceroute on an Atlas probe on your network or in
your country. Atlas measurements are **public**: RIPE publishes the target, the
probe and the result. The app asks you to confirm that before the first one.
Your coordinates are never sent; a probe is chosen by network and country. Each
trace costs 30 of your credits.

## Privacy

No telemetry and no automatic update checks. What leaves the machine, and only
when you trace or open a trace: router hostnames to CAIDA Hoiho, public hop
addresses to RIPEstat, PTR queries to your own DNS resolver, one public IP
lookup unless you set an origin, and RIPE Atlas only if you enable it. Private,
CGNAT and reserved addresses are never looked up. Details in
[PRIVACY.md](PRIVACY.md) and in the app under **Help > Privacy**.

## Adding a carrier to the site-code table

The table only ever contains a carrier's **own published** router list, applied
only to that carrier's backbone hostnames. See
[routemap/engine/data/README.md](routemap/engine/data/README.md): add the source
to the generator, declare the carrier's zones, run `routemap sites update`, and
add a test case.

## Verifying downloads

Each release has a `SHA256SUMS` file: `sha256sum -c SHA256SUMS --ignore-missing`.
From 0.1.0 the Windows binary will be Authenticode-signed and `SHA256SUMS`
GPG-signed, with the key fingerprint published here.

## The engine

```python
from routemap.engine import analyse_sync, run_trace, TraceOptions

result = run_trace("heise.de", TraceOptions(on_line=print))   # system traceroute
route = analyse_sync(result.text, origin=(14.6, 121.0))
route.to_dict()   # the route model; schema in routemap/engine/route.schema.json
```

Pure Python, no Qt. See [docs/engine.md](docs/engine.md).

## Credits

- [CAIDA Hoiho](https://api.hoiho.caida.org/): router hostname geolocation rules.
- [RIPE NCC](https://stat.ripe.net/): RIPEstat IP geolocation, and RIPE Atlas.
- [GeoNames](https://www.geonames.org/): the city list (cities15000), used under
  [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).
- [Natural Earth](https://www.naturalearthdata.com/): the world map (public domain).
- Arelion's public looking glass: the carrier's own router site list.
- [Qt](https://www.qt.io/) via PySide6.

## Licence

GNU Affero General Public License v3.0. See [LICENSE](LICENSE).
