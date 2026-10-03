"""
Put the two standalone Windows builds into one folder and finish the exes.

    python packaging/assemble_windows.py  -> build/nuitka/windows/Route Map/

1. Copy build/nuitka/entry_gui.dist (routemap.exe) to the target folder, then
   add build/nuitka/entry_cli.dist (routemap-cli.exe). The two builds share
   the Python runtime, Qt and the compiled extension modules; a file present in
   both must be byte-identical, or the build fails rather than ship a mix.
2. Embed packaging/windows/routemap.manifest in both exes as resource 1, with
   the Windows SDK's mt.exe, and read it back to check it is there.
3. Add LICENSE, NOTICE and THIRD_PARTY_NOTICES.md.
"""
from __future__ import annotations

import filecmp
import glob
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "nuitka"
sys.path.insert(0, str(ROOT))
# Not "from packaging import ...": that name is the pip "packaging" library.
sys.path.insert(0, str(ROOT / "packaging"))
from routemap.__about__ import DISPLAY_NAME  # noqa: E402
from build_nuitka import numeric_version  # noqa: E402

TARGET = OUT / "windows" / DISPLAY_NAME
EXES = ("routemap.exe", "routemap-cli.exe")


def mt_exe() -> str:
    found = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\mt.exe"))
    if not found:
        sys.exit("mt.exe not found: install the Windows 10/11 SDK")
    return found[-1]


def merge(gui: pathlib.Path, cli: pathlib.Path) -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(gui, TARGET)
    conflicts = []
    for src in cli.rglob("*"):
        rel = src.relative_to(cli)
        dst = TARGET / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        elif dst.exists():
            if not filecmp.cmp(src, dst, shallow=False):
                conflicts.append(str(rel))
        else:
            shutil.copy2(src, dst)
    if conflicts:
        sys.exit("the GUI and CLI builds disagree on: " + ", ".join(conflicts[:20]))


def embed_manifest(mt: str) -> None:
    template = (ROOT / "packaging" / "windows" / "routemap.manifest").read_text(encoding="utf-8")
    manifest = OUT / "windows" / "routemap.manifest"
    manifest.write_text(template.replace("@VERSION@", numeric_version()), encoding="utf-8")
    for exe in EXES:
        path = TARGET / exe
        subprocess.run([mt, "-nologo", "-manifest", str(manifest),
                        f"-outputresource:{path};#1"], check=True)
        back = OUT / "windows" / f"{exe}.manifest"
        subprocess.run([mt, "-nologo", f"-inputresource:{path};#1", f"-out:{back}"], check=True)
        text = back.read_text(encoding="utf-8", errors="replace")
        for needle in ("OSINTPH.RouteMap", "asInvoker", "PerMonitorV2", "8e0f7a12"):
            if needle not in text:
                sys.exit(f"{exe}: embedded manifest lacks {needle}")
        print(f"{exe}: manifest embedded and read back")


def main() -> int:
    merge(OUT / "entry_gui.dist", OUT / "entry_cli.dist")
    embed_manifest(mt_exe())
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, TARGET / name)
    files = sum(1 for p in TARGET.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in TARGET.rglob("*") if p.is_file())
    print(f"{TARGET}: {files} files, {size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
