"""Release notes: how to install (and verify) first, then this version's
CHANGELOG section, which lists what changed.

    python packaging/release_notes.py v0.1.0-beta.4 [--fingerprint FPR] [--windows-signed]

Without --windows-signed the notes say the Windows build is not code-signed and
give the SmartScreen steps; with it, they say it is signed through SignPath
Foundation.
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from routemap.__about__ import REPO_URL  # noqa: E402

WINDOWS_UNSIGNED = (
    "- **Windows 10/11**: download `routemap-<version>-windows-x86_64.zip`, "
    "extract it, and run `routemap.exe` in the `Route Map` folder (keep the folder "
    "together; `routemap-cli.exe` beside it is the command line). **The Windows "
    "build is not code-signed yet** (signing through SignPath Foundation is "
    "pending): SmartScreen says \"Windows protected your PC\"; choose **More "
    "info**, then **Run anyway**.")
WINDOWS_SIGNED = (
    "- **Windows 10/11**: download `routemap-<version>-windows-x86_64.zip`, "
    "extract it, and run `routemap.exe` in the `Route Map` folder (keep the folder "
    "together; `routemap-cli.exe` beside it is the command line). Both exes are "
    "code-signed: free code signing provided by SignPath.io, certificate by "
    "SignPath Foundation.")
REST = """- **macOS 12+**: open the `.dmg` for your Mac (`macos-arm64` for Apple silicon,
  `macos-x86_64` for Intel) and drag Route Map to Applications. The app is not
  notarised yet, so Gatekeeper blocks the first start: **right-click** it,
  choose **Open**, then **Open** again (on macOS 15, System Settings > Privacy &
  Security > **Open Anyway**). Or: `xattr -d com.apple.quarantine "/Applications/Route Map.app"`.
- **Linux x86_64**: `chmod +x` the `.AppImage` and run it, or unpack the
  `.tar.gz` and run `./routemap`. Tracing needs `traceroute` installed."""


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
        (WINDOWS_SIGNED if windows_signed else WINDOWS_UNSIGNED) + "\n" + REST,
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
