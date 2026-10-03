# Route Map

**See where your traffic physically goes.** Route Map runs a traceroute from
your own computer, or reads one you paste, and draws the path on a world map
with a hop table beside it. Free and open source (GNU AGPL-3.0), for macOS,
Windows and Linux.

It follows three rules:

1. **Hostname first.** A router's DNS name usually says where it is
   (`ae1.fra10...` is Frankfurt). Route Map reads it with CAIDA's Hoiho rules
   and carrier site codes before it ever asks an IP database.
2. **Physics checked.** A hop cannot be farther away than light in fibre gets
   in its round-trip time. A placement that breaks that bound is rejected,
   whatever the database says.
3. **Honest labels.** Every placement says where it came from; a hop placed
   only to a country is drawn hollow, and a hop that cannot be placed is listed
   with the reason, not guessed.

The trace runs on your machine with the system's own `tracert`, `traceroute`
or `mtr`. Nothing about it is sent anywhere except the lookups listed in
[PRIVACY.md](PRIVACY.md).

## Install

Download the latest release from
[GitHub Releases](https://github.com/osintph/routemap/releases).

| Platform | File | First run |
|---|---|---|
| Windows 10/11 | `routemap-<version>-windows-x86_64` | Not code-signed yet: SmartScreen says "Windows protected your PC"; choose **More info**, then **Run anyway**. |
| macOS 12+ (Apple silicon) | `routemap-<version>-macos-arm64.dmg` | Drag Route Map to Applications. Not notarised: right-click it, **Open**, then **Open** again. |
| macOS 12+ (Intel) | `routemap-<version>-macos-x86_64.dmg` | As above. |
| Linux x86_64 | `.AppImage` or `.tar.gz` | `chmod +x` the AppImage and run it. Tracing needs `traceroute` (`sudo apt install traceroute`). |

The Windows download also has `routemap-cli`, the command-line version.

### Verify a download

Each release has `SHA256SUMS` and its GPG signature `SHA256SUMS.asc`, made
with the release key `D57C 7E26 C19F 9436 E2D6  6F37 4080 97D1 91DD F981`.

```bash
gpg --verify SHA256SUMS.asc SHA256SUMS
sha256sum -c SHA256SUMS --ignore-missing          # Linux
shasum -a 256 -c SHA256SUMS --ignore-missing      # macOS
```

On Windows: `Get-FileHash <file>` in PowerShell, compared with `SHA256SUMS`.

## Command line

```bash
routemap example.com                      # trace, then open the window
routemap example.com --json > route.json  # trace, print the route as JSON
routemap parse trace.txt --png map.png    # map a trace run elsewhere
routemap --help
```

## Develop

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[gui,dev]"
.venv/bin/python -m pytest -q
.venv/bin/routemap
```

The geolocation engine is a separate package,
[routemap-engine](https://github.com/osintph/routemap-engine) (AGPL-3.0),
also used by FalconEye. Engine changes go there.

Builds: `packaging/build_nuitka.py` compiles each platform with Nuitka, and
`.github/workflows/build.yml` builds, verifies and smoke-tests every platform
on a tag, then publishes the release.

## Contributing

Issues and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).
Pull requests need the [Contributor Licence Agreement](CLA.md), signed once
with a comment, and may be declined.

## Licence

GNU AGPL-3.0 or later; see [LICENSE](LICENSE). Third-party components and
data keep their own licences: [NOTICE](NOTICE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) (also in the app, Help >
Third-Party Notices).
