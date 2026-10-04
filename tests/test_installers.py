"""The installer sources agree with each other and with the build."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging" / "windows"))
sys.path.insert(0, str(ROOT / "packaging" / "linux"))

import iss_defines  # noqa: E402
import make_packages  # noqa: E402

from routemap.__about__ import DISPLAY_NAME, NAME  # noqa: E402


def test_the_upgrade_identity_is_the_same_in_the_installer_and_its_check():
    iss = (ROOT / "packaging/windows/routemap.iss").read_text()
    check = (ROOT / "packaging/windows/install_check.ps1").read_text()
    guid = re.search(r'#define AppGuid "([0-9A-F-]{36})"', iss).group(1)
    assert "{" + guid + "}_is1" in check


def test_every_define_the_installer_uses_is_passed():
    iss = (ROOT / "packaging/windows/routemap.iss").read_text()
    used = set(re.findall(r"\{#(\w+)\}", iss)) - {"AppGuid"}
    passed = {a[2:].split("=")[0] for a in iss_defines.defines("0.2.0b1", "a" * 40, "7", "src", "out")
              if a.startswith("/D")}
    assert used <= passed, used - passed


def test_installer_names_and_versions_come_from_about():
    args = iss_defines.defines("0.2.0b1", "54455e58a0f5" + "0" * 28, "41", "src", "out")
    assert f"/DAppName={DISPLAY_NAME}" in args and f"/DGuiExe={NAME}.exe" in args
    assert "/DNumericVersion=0.2.0.41" in args and "/DAppVersion=0.2.0b1+54455e5" in args
    cfg = make_packages.config("/b/routemap", "0.2.0b1", "41")
    assert (cfg["name"], cfg["version"], cfg["prerelease"], cfg["release"]) == (NAME, "0.2.0", "b1", "41")
    assert make_packages.config("/b/routemap", "0.2.0", "41").get("prerelease") is None
    dsts = {c["dst"] for c in cfg["contents"]}
    assert {f"/usr/bin/{NAME}", f"/usr/share/applications/{NAME}.desktop", f"/usr/share/pixmaps/{NAME}.png"} <= dsts


def test_the_packages_declare_what_the_build_machine_installs_for_qt():
    build = (ROOT / ".github/workflows/build.yml").read_text()
    for deb in make_packages.LIBS:
        assert re.search(rf"\b{re.escape(deb)}\b", build), deb
