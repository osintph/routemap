# Testing a beta

Thank you for testing Route Map. A beta is a release we want tried on real
machines and real networks before it is final. This page says how to install
one, what to look at, and how to tell us what you found.

## Get the build

Betas are on [GitHub Releases](https://github.com/osintph/routemap/releases),
marked *Pre-release*, with the same files and the same GPG-signed
`SHA256SUMS` as any release. If we gave you a login for the pre-release
download site, the builds there are the same files, sometimes a few days
earlier.

Take the installer for your system:

| System | File |
|---|---|
| Windows 10/11 | `routemap-<version>-windows-x86_64-setup.exe` |
| macOS, Apple silicon | `routemap-<version>-macos-arm64.dmg` |
| macOS, Intel | `routemap-<version>-macos-x86_64.dmg` |
| Debian, Ubuntu and relatives | `routemap-<version>-linux-x86_64.deb` |
| Fedora, RHEL, openSUSE | `routemap-<version>-linux-x86_64.rpm` |

The [download page](https://getroutemap.app/download/) has the install,
upgrade and uninstall steps, and what to do when Windows SmartScreen or macOS
Gatekeeper stops the first start.

## Check what you have

**Help > About** shows the version, the commit it was built from and the
engine version (with the engine's commit while that is not a published
release). `routemap --version` (Linux, macOS) or `routemap-cli.exe --version`
(Windows) prints the same two lines. Please put them in every report: it is how
we know exactly which build you ran.

## What to try

- **Trace** two or three places you know: a site in your own country, one on
  another continent, and one you reach through a VPN or a mobile hotspot if you
  can. Do the hop locations look right? Is anything placed somewhere the round
  trip time makes impossible?
- **The header above the map** names the prober ("Built-in ICMP prober") and
  the Hoiho ruleset date. Round trip times should have decimals on every
  platform.
- **The route summary**: AS path, RIS paths, the BGP 48 hour chart (the last
  hours may be hatched while RIPEstat's data catches up), RPKI.
- **Globe and flat map** (Ctrl+G), zoom and pan with a mouse wheel, a trackpad
  and the keyboard.
- **Compare** two traces to the same place (Trace > Trace Again and Compare).
- **Export** PNG, PDF and JSON (File > Export…), and open the PDF.
- **Theme**: System, Light and Dark (View > Theme).
- **Install, upgrade and uninstall**: install over the previous beta, check your
  history is still there, then uninstall and check the Start menu entry
  (Windows) or the menu entry (Linux) is gone.
- **Help > Check for Updates**: it should say you have the latest release, or
  offer the right file for your system.

## Report what you found

Open an issue at
[github.com/osintph/routemap/issues](https://github.com/osintph/routemap/issues)
or write to support@getroutemap.app with:

1. the two lines from Help > About,
2. your system (for example "Windows 11 24H2", "macOS 15.1 on M2", "Ubuntu 24.04"),
3. what you did, what you expected and what happened,
4. a screenshot, and for a wrong placement the trace itself (File > Export…
   as JSON, or the trace text from View > Tool Output).

**Before you send a trace or a screenshot**, remove what describes your own
network: the first hops are your router and your provider's access network,
and their names and addresses can say where you live. Replace them with
`192.0.2.x` or cut those lines. Route Map never sends a trace anywhere by
itself; what is in a report is only what you choose to send.

## Start over

Uninstalling keeps your settings, history and downloaded databases. To start
from nothing, also delete `%APPDATA%\routemap` (Windows),
`~/Library/Application Support/routemap` (macOS) or `~/.config/routemap`
(Linux).
