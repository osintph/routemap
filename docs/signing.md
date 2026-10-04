# Code signing and antivirus

| Platform | Status |
|---|---|
| Windows | unsigned until signing with the maintainer's Certum certificate is set up; see [CODE_SIGNING_POLICY.md](../CODE_SIGNING_POLICY.md) |
| macOS | unsigned (ad-hoc signature only, which Apple silicon needs to run the app at all) |
| Linux | nothing to sign in the binaries |
| All | `SHA256SUMS` signed with the GPG release key `D57C 7E26 C19F 9436 E2D6 6F37 4080 97D1 91DD F981` |

## Windows signing

Windows releases are to be signed with a Certum code signing certificate paid
for by the maintainer. Until that step is in the build workflow, the release
job publishes the unsigned zip, the release notes say so, and the run summary
reports the Windows build as unsigned. When it is added, the executables are
signed, checked with `signtool verify /pa`, scanned with Defender again, and
`WINDOWS_SIGNED = True` in `routemap/__about__.py` and `windows_signed = true`
in `site/site.toml` drop the unsigned warnings.

## Microsoft Defender

### What happened (0.1.0-beta.3)

On a Windows 11 PC, Defender deleted `routemap-0.1.0b3-windows-x86_64.exe`
straight after download. beta.1 (a PyInstaller build) was not flagged; beta.3
was the first Nuitka build, and it was a one-file exe: a compressed payload
that unpacks itself at start, which antivirus heuristics treat like a packer.

A Defender custom scan on a GitHub Windows runner (engine 1.1.26080.3,
signatures 1.459.537.0, 2026-10-04) did **not** flag the same file, with or
without cloud-delivered protection, while it did detect an EICAR test file. So
the detection on the PC came from a check a scan on a build machine does not
reproduce (most likely reputation of files downloaded from the internet, or
block at first sight). The CI scan therefore guards against signature
detections only; a clean CI scan is not proof that a downloaded build will be
accepted. Signing is the real fix.

### What changed for 0.1.0-beta.4

- Windows is built in Nuitka **standalone (folder) mode**, shipped as a zip,
  not as a one-file self-extractor.
- **No UPX or any other packer**; `packaging/verify_windows.py` fails the build
  if an exe has a packer's section names.
- Both exes carry **full version resources** (company OSINTPH, product Route
  Map, file description, file and product version, copyright) and an
  **application manifest** (`packaging/windows/routemap.manifest`: asInvoker,
  Windows 10/11, per-monitor DPI, long paths), checked on every build.
- **Every Windows artifact is scanned with Defender in CI**
  (`packaging/defender_scan.ps1`, `MpCmdRun -Scan`), with an EICAR control,
  and the build fails on any detection. The scan report is in the build's
  `smoke-windows-x86_64` artifact (`defender.txt`).

### False-positive submission

Submit the exact published file at
https://www.microsoft.com/en-us/wdsi/filesubmission, signed in, as
**Software developer**, "Incorrectly detected as malware/malicious".

| Field | Value |
|---|---|
| File | `routemap-0.1.0b3-windows-x86_64.exe` |
| SHA-256 | `521726bb3d157fec625340a5cc3653719c50454eb548f11e8b371d264fd7ce0a` |
| Size | 29,484,032 bytes |
| Detection name | (as shown in Windows Security > Protection history) |
| Product | Microsoft Defender Antivirus (Windows 11) |

Text for the "Additional information" field:

> Route Map is a free, open-source (AGPL-3.0) desktop app that runs a
> traceroute with the system's own tracert and draws the route on a map:
> https://github.com/osintph/routemap. This file is our 0.1.0-beta.3 Windows
> beta, compiled by our GitHub Actions workflow with Nuitka in one-file mode,
> which unpacks the program into a temporary folder at start;
> we believe that is what triggered the detection. It contains no malware, does
> not elevate, and talks only to the services listed in our PRIVACY.md (CAIDA
> Hoiho, RIPEstat, RIPE Atlas with the user's own key, GitHub for an explicit
> update check). The SHA-256 above matches our GPG-signed SHA256SUMS. Our next
> build drops one-file mode (standalone folder, version resources, manifest)
> and will be code-signed. Please review and
> remove the detection.

| Submission | Date | ID | Result |
|---|---|---|---|
| beta.3 Windows exe | (pending) | (record here) | (record here) |
