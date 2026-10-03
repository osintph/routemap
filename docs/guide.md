# Route Map user guide

## Install

Download the latest release from
[GitHub Releases](https://github.com/osintph/routemap/releases) or
[getroutemap.app](https://getroutemap.app/download/).

- **Windows 10/11**: download `routemap-<version>-windows-x86_64.zip`, extract
  it, and run `routemap.exe` in the `Route Map` folder. Keep the folder
  together; you can pin `routemap.exe` to Start or the taskbar. Until the
  build is code-signed, SmartScreen may say "Windows protected your PC":
  choose **More info**, then **Run anyway**. `routemap.exe` never opens a
  console; `routemap-cli.exe` beside it is the command line.
- **macOS 12+**: open the `.dmg` for your Mac (`macos-arm64` for Apple
  silicon, `macos-x86_64` for Intel) and drag Route Map to Applications. The
  app is not notarised, so the first start is blocked: right-click it, choose
  **Open**, then **Open** again (on macOS 15: System Settings > Privacy &
  Security > **Open Anyway**).
- **Linux x86_64**: `chmod +x` the `.AppImage` and run it, or unpack the
  `.tar.gz` and run `./routemap`. Tracing needs `traceroute` (for example
  `sudo apt install traceroute`); `mtr` is used if you prefer it.

Check a download (optional): `gpg --verify SHA256SUMS.asc SHA256SUMS`, then
`sha256sum -c SHA256SUMS --ignore-missing` (Linux),
`shasum -a 256 -c SHA256SUMS --ignore-missing` (macOS) or `Get-FileHash <file>`
(PowerShell). The release key is
`D57C 7E26 C19F 9436 E2D6 6F37 4080 97D1 91DD F981`.

## First trace

1. Type a hostname or IP address in the box at the top and press **Trace**.
2. Hops appear on the map and in the table as the trace runs. The tool's own
   output is under **Tool output** below the table (View > Tool Output).
3. When it finishes, the map fits the route. Zoom with the wheel or pinch,
   drag to pan, **Fit** to see the route again.

Your starting point (the origin) comes from your public IP address until you
set one in **Settings > Origin**: a city, coordinates, or a point picked on
the map. Setting one means the public-IP lookup never happens.

## Reading the map

- **Colours** say where each placement came from: a router hostname rule
  (CAIDA Hoiho), a carrier site code, the IP database fallback, or your local
  network. The legend shows only the sources used.
- **Hollow markers** are placed only to a country ("AT (country only)"). They
  are shown, but the map does not zoom out to fit them.
- **Dashed markers** are hops that did not answer, or that answered but could
  not be placed ("not placed"). The **Unplaced** panel lists them with the
  reason.
- Hops in the same city collapse into one marker ("14-15"). Click a marker to
  select its rows; click a row, or use the arrow keys, to highlight its marker.
  Esc clears.
- Every placement is checked against the round-trip time: a hop cannot be
  farther away than light in fibre travels in that time, so an impossible
  database answer is rejected and said so in **Notes**.

## Other ways to get a trace

- **Paste Trace** (File menu, Ctrl+Shift+V): paste the output of `traceroute`,
  `tracert` or `mtr` run anywhere, and set where it was run from.
- **Open Trace**: a saved trace file or a Route Map JSON export.
- **RIPE Atlas**: with your own Atlas API key (Settings > RIPE Atlas), trace
  from a probe on your network. Atlas measurements are public; the app asks
  you to confirm this once.

## Exports

**File > Export**: PNG (the map with legend), PDF (map, hop table, sources
and the raw trace), or JSON (everything, to open again later). The command
line does the same; see [cli.md](cli.md).

## Privacy

Nothing is sent anywhere until you run or open a trace, and then only what
[PRIVACY.md](../PRIVACY.md) lists (also Help > Privacy). Each source can be
switched off in Settings; with all of them off, placements come only from the
bundled carrier site codes.

## Reporting a problem

Please [open an issue on GitHub](https://github.com/osintph/routemap/issues).
If you would rather not use GitHub, use the email address on
[getroutemap.app/support](https://getroutemap.app/support/). What helps
most: your OS and version, the Route Map version (Help > About), what you
traced, what you expected, and a screenshot or a JSON export (File > Export).
A JSON export contains the trace, so leave it out if the path is private.
