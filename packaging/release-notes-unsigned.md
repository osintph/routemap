

---

### This build is not signed yet

Code signing arrives before 0.1.0. Until then your system will warn you:

- **macOS** (`.dmg`): drag Route Map to Applications. The first time, right-click
  it and choose **Open**, then **Open** again; or run
  `xattr -d com.apple.quarantine "/Applications/Route Map.app"`. This is expected
  for an app that is not yet notarised by Apple.
- **Windows** (`.exe`): SmartScreen says "Windows protected your PC". Choose
  **More info**, then **Run anyway**.
- **Linux** (`.AppImage` or `.tar.gz`): `chmod +x` the file and run it. Check
  it against `SHA256SUMS` with `sha256sum -c SHA256SUMS --ignore-missing`.

Each binary is 60 to 110 MB because it carries its own copy of Qt.
