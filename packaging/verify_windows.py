"""
Prove on a Windows runner that routemap.exe is a windowed program.

    python packaging/verify_windows.py dist\\routemap.exe dist\\routemap-cli.exe

1. Subsystem. The PE header of routemap.exe must say WINDOWS_GUI (2), so neither
   a double-click nor a shortcut ever creates a console for it, and that of
   routemap-cli.exe must say WINDOWS_CUI (3).
2. Not packed, and described. No section of either exe has a packer's name
   (UPX, ASPack, MPRESS and the like), and both carry full version resources
   (company, product, description, file and product version, copyright).
3. Survival. routemap.exe is started from a console process (cmd.exe in a new
   console), that console process is killed outright, and the app must keep
   running: its heartbeat keeps advancing and it reaches its own clean exit.
   The app also records whether it has a console window attached: it must not.
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import time

GUI, CUI = 2, 3


def subsystem(path: str) -> int:
    with open(path, "rb") as handle:
        data = handle.read(4096)
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[pe:pe + 4] == b"PE\0\0", f"{path} is not a PE file"
    optional = pe + 24
    return struct.unpack_from("<H", data, optional + 68)[0]


# Section names that packers and protectors leave behind. A packed exe is the
# classic antivirus false-positive trigger, so none may appear.
PACKER_SECTIONS = ("upx", ".aspack", ".adata", "mpress", ".petite", "pec2", ".nsp",
                   ".packed", ".themida", ".vmp", "pebundle", ".enigma", ".mpress")


def sections(path: str) -> list[str]:
    with open(path, "rb") as handle:
        data = handle.read(65536)
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    table = pe + 24 + optional_size
    return [data[table + 40 * i: table + 40 * i + 8].rstrip(b"\0").decode("latin-1")
            for i in range(count)]


def version_info(path: str) -> dict:
    script = (f"(Get-Item -LiteralPath '{path}').VersionInfo | Select-Object CompanyName,"
              "ProductName,FileDescription,FileVersion,ProductVersion,LegalCopyright | ConvertTo-Json")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def check_resources(path: str) -> None:
    names = sections(path)
    print(f"{os.path.basename(path)}: sections {names}")
    packed = [n for n in names if n.lower().startswith(PACKER_SECTIONS)]
    assert not packed, f"{path} has packer sections {packed}"
    info = version_info(path)
    print(f"{os.path.basename(path)}: {info}")
    missing = [k for k, v in info.items() if not (v or "").strip()]
    assert not missing, f"{path} lacks version resources {missing}"


def main(gui: str, cli: str) -> int:
    check_resources(gui)
    check_resources(cli)
    gui_sub, cli_sub = subsystem(gui), subsystem(cli)
    print(f"{os.path.basename(gui)}: subsystem {gui_sub} (2 = Windows GUI)")
    print(f"{os.path.basename(cli)}: subsystem {cli_sub} (3 = console)")
    assert gui_sub == GUI, "routemap.exe is not a windowed program"
    assert cli_sub == CUI, "routemap-cli.exe is not a console program"

    out = tempfile.mkdtemp(prefix="routemap-hold-")
    hold = 25
    parent = subprocess.Popen(
        ["cmd.exe", "/k", os.path.abspath(gui), "--smoke-hold", str(hold), out],
        creationflags=subprocess.CREATE_NEW_CONSOLE)
    deadline = time.time() + 60
    while not os.path.exists(os.path.join(out, "hold.json")) and time.time() < deadline:
        time.sleep(0.5)
    assert os.path.exists(os.path.join(out, "hold.json")), "routemap.exe never started"
    info = json.load(open(os.path.join(out, "hold.json"), encoding="utf-8"))
    print(f"app pid {info['pid']}, parent pid {info['ppid']} (console cmd.exe was {parent.pid}), "
          f"console window handle {info['console_window']}, platform {info['platform']}")
    assert info["console_window"] == 0, "routemap.exe has a console window attached"

    time.sleep(3)
    subprocess.run(["taskkill", "/F", "/PID", str(parent.pid)], check=False,
                   capture_output=True)
    parent.wait(timeout=10)
    print(f"killed the console process {parent.pid}")
    beat_path = os.path.join(out, "heartbeat")
    before = int(open(beat_path).read() or 0)
    time.sleep(5)
    after = int(open(beat_path).read() or 0)
    print(f"heartbeat {before} -> {after} after the console was killed")
    assert after > before, "routemap.exe stopped when its console was killed"
    deadline = time.time() + hold + 30
    while not os.path.exists(os.path.join(out, "done")) and time.time() < deadline:
        time.sleep(1)
    assert os.path.exists(os.path.join(out, "done")), "routemap.exe did not reach its clean exit"
    print("ok: windowed, no console, survived its console being killed, exited cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
