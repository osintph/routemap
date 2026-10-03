# Code signing

| Platform | Status |
|---|---|
| Windows | unsigned for now; applying to SignPath Foundation (free signing for open-source projects). See [CODE_SIGNING_POLICY.md](../CODE_SIGNING_POLICY.md) once added. |
| macOS | unsigned (ad-hoc signature only, which Apple silicon needs to run the app at all) |
| Linux | nothing to sign in the binaries |
| All | `SHA256SUMS` is signed with the project's GPG release key |

## Windows

Windows builds are made only by the public workflow in this repository. The
signing seam is `.github/actions/sign-windows/action.yml`; until a provider is
approved, Windows artifacts are unsigned and the release notes say so, with the
SmartScreen steps.

## Checksums and GPG

Every release has `SHA256SUMS` and `SHA256SUMS.asc`, a detached signature made
with the release key (secrets `GPG_RELEASE_KEY` and `GPG_RELEASE_PASSPHRASE`).
Its fingerprint is in the README and the release notes.

## macOS

Unsigned (ad-hoc) until enabled. Developer ID signing and notarisation would be
switched on by the variable `APPLE_SIGNING=true` with an Apple Developer Program
certificate and an App Store Connect API key as secrets.
