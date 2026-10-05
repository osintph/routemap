# Troubleshooting

## Windows: Defender removes or blocks the download

The Windows build is not code-signed yet, so Microsoft Defender and SmartScreen
have no reputation for it. 0.1.0-beta.3, a single self-extracting exe, was
quarantined as a false positive; since 0.1.0-beta.4 Windows gets a normal
program folder with version information and a manifest (since 0.2.0-beta.2 as
an installer, and still as a zip), and every build, installer included, is
scanned with Defender before release.

If Defender still removes it:

1. Check the file is ours: compare `Get-FileHash <file>` in PowerShell with the
   release's GPG-signed `SHA256SUMS` (see the [user guide](guide.md#install)).
2. Open **Windows Security > Virus & threat protection > Protection history**,
   find the entry, and note the detection name.
3. Please report it, with the detection name and the version, at
   [GitHub Issues](https://github.com/osintph/routemap/issues) or
   support@getroutemap.app. We submit false positives to Microsoft.
4. To keep the file meanwhile, choose **Actions > Restore** on that entry (only
   after step 1).

## Windows: "Windows protected your PC"

That is SmartScreen, shown for programs without download reputation. Choose
**More info**, then **Run anyway**. It goes away once the build is
code-signed.

## Windows: the installer asks for administrator rights

Choose **Install for me only** on its first page: Route Map then installs into
your user folder (`%LOCALAPPDATA%\Programs\Route Map`) without administrator
rights. **Install for all users** puts it in Program Files and needs them.
From a terminal: `routemap-<version>-windows-x86_64-setup.exe /CURRENTUSER`.

## A summary section says "unavailable"

The route summary's online parts come from RIPEstat and RIPE Atlas. When one
does not answer, the section stays and says why, for example "RIPEstat did not
answer within 20 s". Trace again later, or check that Settings > Sources >
Online lookups is on. Help > About shows the exact version and commit.

## Linux: traces use traceroute instead of ICMP

The built-in ICMP prober needs unprivileged ICMP sockets, which most desktop
distributions allow. If yours does not, Settings > Trace says so and traces
use `traceroute` (UDP). To allow it for all users (as root):
`sysctl -w net.ipv4.ping_group_range="0 2147483647"`, and add that line to
`/etc/sysctl.d/99-ping.conf` to keep it after a restart.

## macOS: "Route Map cannot be opened" or "Apple could not verify"

The app is not notarised. Right-click Route Map in Applications, choose
**Open**, then **Open** again. On macOS 15 and later: try to open it once, then
**System Settings > Privacy & Security**, and **Open Anyway** next to the
message about Route Map. Or in Terminal:

```bash
xattr -d com.apple.quarantine "/Applications/Route Map.app"
```

## No trace tool found

The status bar says which tool is missing and how to install it.

- **Linux**: `sudo apt install traceroute` (Debian, Ubuntu),
  `sudo dnf install traceroute` (Fedora), `sudo pacman -S traceroute` (Arch).
  `mtr` is optional and adds per-hop loss (`sudo apt install mtr-tiny`).
- **macOS**: `traceroute` ships in `/usr/sbin`, where Route Map looks first (then
  `/usr/bin`, `/sbin`, `/bin`, then the absolute folders on your PATH).
- **Windows**: Route Map runs `tracert.exe` from the Windows system folder
  (`C:\Windows\System32`) only, never a copy on PATH or in the current folder.

You can still map traces without a local tool: **File > Paste Trace**, or a RIPE
Atlas probe (Settings > RIPE Atlas).

## The origin is in the wrong place (VPN, proxy, exit node)

Without a set origin, Route Map looks up your public IP address to find your
city. Behind a VPN, a corporate proxy or a Tor exit, that is the exit's location,
not yours, and every physics check is then measured from the wrong place. Set
your real origin in **Settings > Origin** (a city, coordinates, or a point on the
map). Note that the trace itself also leaves through the VPN, so the first hops
after your router are the VPN's.

## Most hops say "not placed"

Hops that do not answer (`*`) cannot be placed, and many backbone routers
answer slowly or not at all. A trace that stops answering near the end usually
means the destination or its firewall drops the probes; the Notes column says
when the destination does not answer ICMP. Try `mtr` (Settings > Trace), or
switch the IP database fallback back on if you turned it off.

## The trace takes a long time

Unanswered hops each wait for a timeout. **Settings > Trace > Give up after**
caps one trace; the default flags already use short waits.
