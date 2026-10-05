"""Release notes: how to install (and verify) first, then this version's
CHANGELOG section, which lists what changed.

    python packaging/release_notes.py v0.1.0-beta.4 [--fingerprint FPR] [--windows-signed]

Without --windows-signed the notes say the Windows build is not code-signed and
give the SmartScreen steps; with it, they say both executables are signed.
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from routemap.__about__ import REPO_URL  # noqa: E402

WINDOWS = (
    "- **Windows 10/11**: run `routemap-<version>-windows-x86_64-setup.exe` and choose "
    "**Install for me only** (no administrator rights, in your user folder) or **Install "
    "for all users** (always Program Files). Route Map is then in the Start menu and in Settings > "
    "Apps, with an uninstaller; `routemap-cli.exe` beside it is the command line (tick "
    "\"Add routemap-cli.exe to PATH\" to use it in any terminal). Without installing: "
    "extract `routemap-<version>-windows-x86_64.zip` and run `routemap.exe` in the "
    "`Route Map` folder.")
WINDOWS_UNSIGNED = WINDOWS + (
    " **This build is not code-signed yet**: SmartScreen says \"Windows protected your "
    "PC\"; choose **More info**, then **Run anyway**.")
WINDOWS_SIGNED = WINDOWS + (
    " The installer, its uninstaller and both executables are signed with the "
    "maintainer's Certum code signing certificate.")
REST = """- **macOS 12+**: open the `.dmg` for your Mac (`macos-arm64` for Apple silicon,
  `macos-x86_64` for Intel) and drag Route Map to Applications. The app is not
  notarised yet, so Gatekeeper blocks the first start: **right-click** it,
  choose **Open**, then **Open** again (on macOS 15, System Settings > Privacy &
  Security > **Open Anyway**). Or: `xattr -d com.apple.quarantine "/Applications/Route Map.app"`.
- **Linux x86_64**: on Debian, Ubuntu and their relatives,
  `sudo apt install ./routemap-<version>-linux-x86_64.deb`; on Fedora, RHEL and
  openSUSE, `sudo dnf install ./routemap-<version>-linux-x86_64.rpm` (or `zypper
  install`). Route Map is then in the applications menu and `routemap` on the
  PATH. Without installing: `chmod +x` the `.AppImage` and run it, or unpack the
  `.tar.gz` and run `./routemap`. Where the distribution does not allow
  unprivileged ICMP, traces use `traceroute` (UDP), which then has to be installed.

**Upgrade**: install the new version over the old one (the Windows installer,
the package manager or the new DMG); settings, history and downloaded databases
stay. Help > Check for Updates links the right file for your system.

**Uninstall**: Windows, Settings > Apps > Route Map > Uninstall; macOS, move
Route Map to the Trash; Linux, `sudo apt remove routemap` or `sudo dnf remove
routemap`. Settings and history stay until you delete their folder:
`%APPDATA%\\routemap` (Windows), `~/Library/Application Support/routemap`
(macOS), `~/.config/routemap` (Linux)."""


def notes(tag: str, fingerprint: str = "", windows_signed: bool = False) -> str:
    version = tag.lstrip("v")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\].*?$(.*?)(?=^## \[|\Z)", changelog, re.M | re.S)
    body = match.group(1).strip() if match else f"Release {version}."
    fpr = " ".join(fingerprint[i:i + 4] for i in range(0, len(fingerprint), 4)) if fingerprint else ""
    verify = ("**Verify a download**: import the release key "
              f"([RELEASE-KEY.asc]({REPO_URL}/blob/main/RELEASE-KEY.asc)) with `gpg --import`, then "
              "`gpg --verify SHA256SUMS.asc SHA256SUMS`"
              + (f" (key `{fpr}`)" if fpr else "")
              + ", then `sha256sum -c SHA256SUMS --ignore-missing` (Linux), "
                "`shasum -a 256 -c SHA256SUMS --ignore-missing` (macOS), or "
                "`Get-FileHash <file>` in PowerShell.")
    return "\n\n".join([
        "## Install",
        ((WINDOWS_SIGNED if windows_signed else WINDOWS_UNSIGNED) + "\n" + REST)
        .replace("<version>", version),
        verify,
        f"Problems or ideas: [open an issue]({REPO_URL}/issues).",
        "---",
        body,
    ]) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("--fingerprint", default="")
    parser.add_argument("--windows-signed", action="store_true")
    args = parser.parse_args(argv)
    sys.stdout.write(notes(args.tag, args.fingerprint, args.windows_signed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
