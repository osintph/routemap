# Code signing policy

Route Map's Windows releases are to be signed with a Certum code signing
certificate paid for and held by the maintainer.

*Until signing is set up in the release workflow, Windows builds are unsigned,
and the release notes of each unsigned release say so.*

## What is signed

Only `routemap.exe` and `routemap-cli.exe` from the Windows release of this
repository, [osintph/routemap](https://github.com/osintph/routemap), built by
its public GitHub Actions workflow
([.github/workflows/build.yml](.github/workflows/build.yml)) on GitHub-hosted
runners from a tagged commit of this public repository.

Never signed with this certificate:

- binaries built anywhere else (a developer's machine, another CI, another
  repository);
- third-party software, or files not built from this repository's source.

## Roles

| Role | Who |
|---|---|
| Author (committer) | [osintph](https://github.com/osintph) |
| Reviewer | [osintph](https://github.com/osintph) |
| Approver | [osintph](https://github.com/osintph) |

Contributions from others reach the repository only through pull requests,
reviewed by the maintainer, from contributors who have signed the
[Contributor Licence Agreement](CLA.md).

## How a release is signed

1. A release tag on this repository starts the build workflow on GitHub-hosted
   runners. It compiles, verifies and smoke-tests the Windows build and scans
   it with Microsoft Defender.
2. The two executables are signed with the maintainer's certificate, and the
   signatures are verified (`signtool verify /pa`).
3. The signed files are scanned again and published on
   [GitHub Releases](https://github.com/osintph/routemap/releases) with a
   GPG-signed `SHA256SUMS`.

## Account security

Multi-factor authentication is required for every account with write access
to this repository and for the certificate account.

## Contact

support@getroutemap.app. Security reports can be encrypted to the release key
([RELEASE-KEY.asc](RELEASE-KEY.asc)).

## Privacy

Route Map has no telemetry and no account. The online services it queries, and
exactly what each receives, are listed in [PRIVACY.md](PRIVACY.md) and in the
app under Help > Privacy: CAIDA Hoiho (router hostnames), RIPEstat (public hop
addresses, and the user's public IP to find the origin when none is set), the
user's own DNS resolver (reverse DNS), RIPE Atlas (only with the user's own key)
and GitHub (only for an explicit update check).
