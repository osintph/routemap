## Install: these builds are not code-signed yet

Your system warns you the first time. That is expected for an unsigned beta.

- **Windows 10/11**: download `routemap-<version>-windows-x86_64.exe` and run
  it. When SmartScreen says "Windows protected your PC", choose **More info**,
  then **Run anyway**. `routemap.exe` is the app and never opens a console. For
  the command line, also download `routemap-cli-<version>-windows-x86_64.exe`
  and run it from a terminal (SmartScreen asks for it separately).
- **macOS 12+**: open the `.dmg` for your Mac (`macos-arm64` for Apple silicon,
  `macos-x86_64` for Intel) and drag Route Map to Applications. The first time,
  **right-click** it, choose **Open**, then **Open** again. If there is no Open
  button: `xattr -d com.apple.quarantine "/Applications/Route Map.app"`.
- **Linux x86_64**: `chmod +x` the `.AppImage` and run it, or unpack the
  `.tar.gz` and run `./routemap`. Tracing needs `traceroute` installed.

Check a download: `gpg --verify SHA256SUMS.asc SHA256SUMS` (the key's fingerprint
is on the download page), then `sha256sum -c SHA256SUMS --ignore-missing` (Linux),
`shasum -a 256 -c SHA256SUMS --ignore-missing` (macOS), or `Get-FileHash <file>`
in PowerShell.

Problems or ideas: reply to your welcome email.
