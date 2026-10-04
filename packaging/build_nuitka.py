"""
Compile the desktop app with Nuitka. One place for every flag.

    python packaging/build_nuitka.py macos           -> build/nuitka/Route Map.app
    python packaging/build_nuitka.py windows-gui     -> build/nuitka/entry_gui.dist/routemap.exe     (no console)
    python packaging/build_nuitka.py windows-cli     -> build/nuitka/entry_cli.dist/routemap-cli.exe (console)
    python packaging/assemble_windows.py             -> build/nuitka/windows/Route Map/ (both, one folder)
    python packaging/build_nuitka.py linux           -> build/nuitka/routemap         (one file)

The app's Python is compiled to C. Qt and PySide6 stay separate shared
libraries, as the LGPL requires.

Windows builds are standalone folders, not one-file executables: a one-file
exe is a self-extracting compressed payload, which antivirus heuristics treat
like a packer (beta.3's one-file exe was deleted by Defender on download). No
UPX or other packer is ever used. Both exes carry full version resources here
and the application manifest from packaging/windows/routemap.manifest
(embedded by assemble_windows.py). The bundled notices and licence texts travel as package data.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "nuitka"
sys.path.insert(0, str(ROOT))
from routemap.__about__ import DISPLAY_NAME, __version__  # noqa: E402

COMMON = [
    "--enable-plugin=pyside6",
    "--include-package-data=routemap_engine",
    "--include-package-data=routemap.gui",
    "--include-package-data=routemap",
    "--include-module=routemap.gui.main",
    "--include-module=routemap.gui.app",
    "--include-module=routemap.gui.legal",
    "--include-module=maxminddb",
    "--nofollow-import-to=jsonschema",
    "--nofollow-import-to=pytest",
    "--nofollow-import-to=PIL",
    "--nofollow-import-to=nuitka",
    "--noinclude-qt-translations",
    "--python-flag=no_docstrings",
    "--assume-yes-for-downloads",
    f"--output-dir={OUT}",
    f"--product-name={DISPLAY_NAME}",
    "--company-name=OSINTPH",
    "--copyright=Copyright (C) 2026 OSINTPH. Free software under the GNU AGPL-3.0.",
    f"--trademarks={DISPLAY_NAME}",
]

# Nothing that packs or compresses executables. Checked here so a flag added
# later cannot slip one in; packaging/verify_windows.py checks the result.
FORBIDDEN = ("upx", "--onefile")


def numeric_version() -> str:
    """'0.1.0b2' -> '0.1.0.2': Windows file versions are four numbers."""
    import re
    match = re.match(r"(\d+\.\d+\.\d+)(?:a|b|rc)?(\d*)", __version__)
    return f"{match.group(1)}.{match.group(2) or 0}"


def run(args: list[str]) -> None:
    print("nuitka", " ".join(args), flush=True)
    subprocess.run([sys.executable, "-m", "nuitka", *args], check=True, cwd=ROOT)


def main(target: str) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    version = ["--file-version=" + numeric_version(), "--product-version=" + numeric_version()]
    if target == "macos":
        # The binary is not called "routemap": that would collide with the
        # routemap/ data folder beside it on a case-insensitive filesystem.
        run(["packaging/entry_cli.py", "--standalone", "--macos-create-app-bundle",
             f"--macos-app-name={DISPLAY_NAME}", "--macos-app-icon=packaging/icon.icns",
             f"--macos-app-version={__version__}", "--output-filename=routemap-app",
             *COMMON])
        app = OUT / f"{DISPLAY_NAME}.app"
        if app.exists():
            shutil.rmtree(app)
        (OUT / "entry_cli.app").rename(app)
        print(app)
    elif target in ("windows-gui", "windows-cli"):
        gui = target == "windows-gui"
        args = [f"packaging/entry_{'gui' if gui else 'cli'}.py", "--standalone",
                f"--windows-console-mode={'disable' if gui else 'force'}",
                "--windows-icon-from-ico=packaging/icon.ico",
                f"--output-filename={'routemap.exe' if gui else 'routemap-cli.exe'}",
                f"--file-description={DISPLAY_NAME}" + ("" if gui else " (command line)"),
                *version, *COMMON]
        bad = [a for a in args if any(f in a.lower() for f in FORBIDDEN)]
        if bad:
            print(f"refusing packer or one-file options on Windows: {bad}", file=sys.stderr)
            return 2
        run(args)
    elif target == "linux":
        # Built under another name for the same collision reason, then renamed:
        # the one-file binary is self-contained, so its name is free.
        run(["packaging/entry_cli.py", "--onefile", "--output-filename=routemap-onefile",
             "--linux-icon=routemap/gui/data/icon.png", *COMMON])
        (OUT / "routemap-onefile").replace(OUT / "routemap")
        print(OUT / "routemap")
    else:
        print(f"unknown target {target!r}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
