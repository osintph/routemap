"""ISCC arguments for packaging/windows/routemap.iss, names from routemap/__about__.py.

    python packaging/windows/iss_defines.py <version> <commit> <build run number> <source dir> <out dir>

prints one ISCC argument per line (PowerShell reads them into an array).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from routemap.__about__ import DISPLAY_NAME, NAME, SITE_URL  # noqa: E402


def defines(version: str, commit: str, run_number: str, source: str, out: str) -> list[str]:
    numeric = ".".join(re.match(r"(\d+)\.(\d+)\.(\d+)", version).groups() + (run_number,))
    short = commit[:7]
    return [
        f"/DAppName={DISPLAY_NAME}",
        f"/DAppVersion={version}+{short}",
        f"/DNumericVersion={numeric}",
        "/DPublisher=OSINTPH",
        f"/DSiteUrl={SITE_URL}",
        f"/DGuiExe={NAME}.exe",
        f"/DCliExe={NAME}-cli.exe",
        f"/DSourceDir={source}",
        f"/O{out}",
        f"/F{NAME}-{version}-{short}-windows-x86_64-setup",
    ]


if __name__ == "__main__":
    print("\n".join(defines(*sys.argv[1:6])))
