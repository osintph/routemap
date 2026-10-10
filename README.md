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

Beside the map: the AS path with RPKI badges, the countries crossed, what
RIPE's route collectors see for the destination, its recent BGP activity and a
typical latency from RIPE Atlas. Flat map or globe, lines coloured by the RTT
each step added, and a comparison with an earlier run.

**Paths** finds every route a load balancer can send your packets along
(Paris traceroute and the multipath detection algorithm, at most 20 probes a
second), each with its own loss and latency. **Reverse trace** asks a RIPE
Atlas probe near the target to trace back to you and compares the two
directions. **Watch** traces continuously, mtr style. All of it over IPv4 or
IPv6.

The trace runs on your machine with the system's own `tracert`, `traceroute`
or `mtr`. Nothing about it is sent anywhere except the lookups listed in
[PRIVACY.md](PRIVACY.md).

## Install

Download the latest release from
[GitHub Releases](https://github.com/osintph/routemap/releases).

| Platform | File | First run |
|---|---|---|
| Windows 10/11 | `routemap-<version>-windows-x86_64.zip` | Extract it and run `routemap.exe` in the `Route Map` folder. Not code-signed yet: SmartScreen may say "Windows protected your PC"; choose **More info**, then **Run anyway**. |
| macOS 12+ (Apple silicon) | `routemap-<version>-macos-arm64.dmg` | Drag Route Map to Applications. Not notarised, so Gatekeeper blocks the first start: right-click it, **Open**, then **Open** again (macOS 15: System Settings > Privacy & Security > **Open Anyway**). |
| macOS 12+ (Intel) | `routemap-<version>-macos-x86_64.dmg` | As above. |
| Linux x86_64 | `.AppImage` or `.tar.gz` | `chmod +x` the AppImage and run it. Tracing needs `traceroute` (`sudo apt install traceroute`). |

**Not on PyPI.** Route Map is not on PyPI: `pip install routemap` installs an
unrelated project of the same name, not this app. Install Route Map only from
[GitHub Releases](https://github.com/osintph/routemap/releases) or
[getroutemap.app](https://getroutemap.app/download/), and check the download
against the signed `SHA256SUMS`. Its engine is on PyPI as `routemap-engine`.

The Windows folder also has `routemap-cli.exe`, the command line.

**Code signing.** The Windows build will be signed with a Certum code
signing certificate paid for by the maintainer; until then it is unsigned and
each release says so. The rules are in
[CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md). macOS builds are not
notarised.

### Verify a download

Each release has `SHA256SUMS` and its GPG signature `SHA256SUMS.asc`, made
with the release key `D57C 7E26 C19F 9436 E2D6  6F37 4080 97D1 91DD F981`
(public key: [RELEASE-KEY.asc](RELEASE-KEY.asc)).

```bash
gpg --import RELEASE-KEY.asc
gpg --verify SHA256SUMS.asc SHA256SUMS
sha256sum -c SHA256SUMS --ignore-missing          # Linux
shasum -a 256 -c SHA256SUMS --ignore-missing      # macOS
```

On Windows: `Get-FileHash <file>` in PowerShell, compared with `SHA256SUMS`.

From 0.2.0-beta.6 each release also has `SHA256SUMS.ed25519`, an Ed25519
signature with the update key over the line `routemap <tag>` followed by
`SHA256SUMS`. Help > Check for Updates checks it with the key built into the
app (`routemap/updatekey.py`) before it installs anything. The update key:

```
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEALvKv5pMRnHidP2qzX+j24fSKbNUiCJuqWfx9aYbkha4=
-----END PUBLIC KEY-----
```

To check it by hand with OpenSSL 3, save that as `update-key.pem`, then:

```bash
{ printf 'routemap %s\n' v0.2.0-beta.6; cat SHA256SUMS; } > message
openssl pkeyutl -verify -rawin -pubin -inkey update-key.pem \
  -sigfile SHA256SUMS.ed25519 -in message
```

## Privacy

No account, no telemetry, no automatic update check. What the app sends, to
whom and when is listed in [PRIVACY.md](PRIVACY.md) and in the app under
Help > Privacy.

## Command line

```bash
routemap example.com                      # trace, then open the window
routemap example.com --json > route.json  # trace, print the route as JSON
routemap parse trace.txt --png map.png    # map a trace run elsewhere
routemap --help
```

Full reference: [docs/cli.md](docs/cli.md). User guide: [docs/guide.md](docs/guide.md).

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

## Support this project

Route Map is free, with no ads and no tracking in the app. Donations pay for code
signing, hosting, the RIPE Atlas probe, and maintenance time.

- Ko-fi: https://ko-fi.com/osintph
- PayPal: https://paypal.me/osintph
- Bitcoin: `bc1q8hn6knzpkp0f2s06qncljpcsatv9dlqan5ttjv`
- Monero: `42kA1yiEM8GSan4FeeZ9MxGtZCLNwYsvGefWLrMJ849dV2o9eVrc1Pufc7LcBAbRebXbVdxC5eoKj1a8pXJ3fSuFUDKLtXM`

The addresses are also in the app under Help > Support Route Map. Bug reports and good trace examples help just
as much.

## Contributing

Issues and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).
Contact: support@getroutemap.app.
Pull requests need the [Contributor Licence Agreement](CLA.md), signed once
with a comment, and may be declined.

## Licence

GNU AGPL-3.0 or later; see [LICENSE](LICENSE). Third-party components and
data keep their own licences: [NOTICE](NOTICE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) (also in the app, Help >
Third-Party Notices).
