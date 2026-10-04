"""Write the nfpm config for the .deb and .rpm, names from routemap/__about__.py.

    python packaging/linux/make_packages.py <binary> <version> <build run number> > nfpm.yaml
    nfpm package -f nfpm.yaml -p deb -t out/ ; nfpm package -f nfpm.yaml -p rpm -t out/

The package installs the build run's one-file binary as /usr/bin/<name> (the
same binary is the app and the CLI), the menu entry and its icon, and the
licence texts. Nothing is recompiled, so it reports the commit that run built.
The release number is the build run's number, so a later build of the same
version still installs as an upgrade.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from routemap.__about__ import NAME, SITE_URL  # noqa: E402

# What the bundled Qt needs from the system for its X11 (xcb) platform and GL;
# the same list the build machine installs. Debian names, and the sonames for
# RPM so one package resolves on Fedora, RHEL and openSUSE alike.
LIBS = {
    "libegl1": "libEGL.so.1", "libgl1": "libGL.so.1",
    "libxkbcommon0": "libxkbcommon.so.0", "libxkbcommon-x11-0": "libxkbcommon-x11.so.0",
    "libfontconfig1": "libfontconfig.so.1", "libdbus-1-3": "libdbus-1.so.3",
    "libxcb-cursor0": "libxcb-cursor.so.0", "libxcb-icccm4": "libxcb-icccm.so.4",
    "libxcb-image0": "libxcb-image.so.0", "libxcb-keysyms1": "libxcb-keysyms.so.1",
    "libxcb-randr0": "libxcb-randr.so.0", "libxcb-render-util0": "libxcb-render-util.so.0",
    "libxcb-shape0": "libxcb-shape.so.0", "libxcb-xinerama0": "libxcb-xinerama.so.0",
}


def config(binary: str, version: str, run_number: str) -> dict:
    release, pre = re.match(r"(\d+\.\d+\.\d+)(.*)", version).groups()
    data = ROOT / "routemap" / "gui" / "data"
    out = {
        "name": NAME, "arch": "amd64", "platform": "linux",
        "version": release, "release": run_number,
        "section": "net", "priority": "optional",
        "maintainer": "osintph <sb@osintph.info>", "vendor": "osintph",
        "homepage": SITE_URL, "license": "AGPL-3.0-or-later",
        "description": "Hostname-first, physics-checked traceroute maps.\n"
                       "Runs the trace on your own machine and draws it on a map.",
        "contents": [
            {"src": binary, "dst": f"/usr/bin/{NAME}", "file_info": {"mode": 0o755}},
            {"src": str(ROOT / "packaging/linux/routemap.desktop"), "dst": f"/usr/share/applications/{NAME}.desktop"},
            {"src": str(data / "icon.png"), "dst": f"/usr/share/pixmaps/{NAME}.png"},
            {"src": str(ROOT / "LICENSE"), "dst": f"/usr/share/doc/{NAME}/LICENSE"},
            {"src": str(ROOT / "NOTICE"), "dst": f"/usr/share/doc/{NAME}/NOTICE"},
            {"src": str(ROOT / "THIRD_PARTY_NOTICES.md"), "dst": f"/usr/share/doc/{NAME}/THIRD_PARTY_NOTICES.md"},
        ],
        "overrides": {
            "deb": {"depends": list(LIBS)},
            "rpm": {"depends": [f"{so}()(64bit)" for so in LIBS.values()]},
        },
    }
    if pre:
        out["prerelease"] = pre  # 0.2.0b1 -> 0.2.0~b1, which sorts before 0.2.0
    return out


if __name__ == "__main__":
    # JSON is valid YAML, and needs nothing beyond the standard library.
    print(json.dumps(config(*sys.argv[1:4]), indent=2))
