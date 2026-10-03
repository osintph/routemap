# SignPath Foundation application: Route Map

Text for the application at https://signpath.org/apply, ready to paste. Submit
it from the maintainer's account; the fields follow the form's order.

## Project

- **Project name:** Route Map
- **Repository:** https://github.com/osintph/routemap
- **Homepage:** https://getroutemap.app
- **Licence:** GNU Affero General Public License v3.0 or later (OSI approved).
  Every file in the repository is under it; third-party components keep their
  own licences (NOTICE, THIRD_PARTY_NOTICES.md).
- **Maintainer:** osintph (OSINTPH, https://osintph.info). Author, reviewer and
  approver for code signing.
- **Contact:** support@getroutemap.app

## What the software does

Route Map is a desktop application for macOS, Windows and Linux that shows
where network traffic physically goes. It runs a traceroute from the user's
own computer with the operating system's own tool (`tracert` on Windows), or
reads a trace the user pastes, and draws the path on an offline world map with
a hop table beside it. It places each router from its DNS name first (CAIDA
Hoiho rules and carrier site codes), checks every placement against the
round-trip time (a hop cannot be farther than light in fibre travels in that
time), and labels every placement with its source. It is used by network
engineers, OSINT and security analysts, and educators.

It has no telemetry, no account and no automatic update check. The online
services it uses, and what each receives, are listed in PRIVACY.md and in the
app (Help > Privacy).

## What would be signed

Two Windows executables from each release: `routemap.exe` (the windowed app)
and `routemap-cli.exe` (the command line), shipped together in a zip.

- Built only by the public GitHub Actions workflow `.github/workflows/build.yml`
  on GitHub-hosted runners, from a tagged commit of the public repository.
- Compiled with Nuitka in standalone (folder) mode: no one-file
  self-extractor, no UPX or other packer. Both exes carry full version
  resources (company, product, description, version, copyright) and an
  application manifest (asInvoker; never elevated).
- Before submission, every build is smoke-tested on the runner and scanned
  with Microsoft Defender; a detection fails the build.
- Submitted with SignPath's GitHub Action
  (`signpath/github-action-submit-signing-request`, pinned by commit), and
  every signing request is approved manually.

## Why signing is needed

The Windows build is unsigned today. SmartScreen warns on every download, and
a previous unsigned build was quarantined by Microsoft Defender as a false
positive on a user's Windows 11 PC. Signing lets users install the app
without disabling protection, and lets them verify that the binary came from
this repository.

## Code signing policy

https://github.com/osintph/routemap/blob/main/CODE_SIGNING_POLICY.md, also
published at https://getroutemap.app/code-signing/. It names the roles,
requires manual approval of every request and MFA on the repository and
SignPath accounts, and limits signing to binaries built by the public workflow
from the public repository.

## Other products

OSINTPH may publish a separate, commercial product in the future, as its own
binary from its own private repository. It is not part of this project and
will never be submitted to or signed with the SignPath Foundation certificate.
This project stays open source under the AGPL; contributions are accepted under
a CLA (CLA.md), which the code signing policy does not change.

## Project status

- First public release line: 0.1.0 betas since 2026-10-03; releases on
  https://github.com/osintph/routemap/releases with a GPG-signed SHA256SUMS
  (key D57C 7E26 C19F 9436 E2D6 6F37 4080 97D1 91DD F981).
- The geolocation engine is a separate AGPL package,
  https://github.com/osintph/routemap-engine, also used by the FalconEye web
  application's Route Map tab.

## The attribution

Once approved, the README, the project site footer, the download page, the
release notes and the app's About box carry: "Free code signing provided by
SignPath.io, certificate by SignPath Foundation". In the code this is one
switch (`SIGNPATH_SIGNED` in `routemap/__about__.py`, and the site config).

## Settings to create in SignPath after approval

- Project slug `routemap`, signing policy `release-signing` (manual approval),
  artifact configuration `windows-folder` from
  `packaging/signpath/artifact-configuration.xml`.
- In the GitHub repository: variable `WINDOWS_SIGNING=signpath`, variable
  `SIGNPATH_ORGANIZATION_ID`, secret `SIGNPATH_API_TOKEN` (a CI user token
  with submitter rights only).
