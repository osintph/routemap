"""The installer sources agree with each other and with the build."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging" / "windows"))
sys.path.insert(0, str(ROOT / "packaging" / "linux"))
sys.path.insert(0, str(ROOT / "packaging"))

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
    args = iss_defines.defines("0.2.0-beta.2", "54455e58a0f5" + "0" * 28, "41", "src", "out")
    assert f"/DAppName={DISPLAY_NAME}" in args and f"/DGuiExe={NAME}.exe" in args
    assert "/DNumericVersion=0.2.0.41" in args and "/DAppVersion=0.2.0-beta.2+54455e5" in args
    assert "/Froutemap-0.2.0-beta.2-windows-x86_64-setup" in args, "a release names it like its other files"
    wrapped = iss_defines.defines("0.2.0-beta.2", "54455e58a0f5" + "0" * 28, "41", "src", "out", commit_in_name=True)
    assert "/Froutemap-0.2.0-beta.2-54455e5-windows-x86_64-setup" in wrapped
    cfg = make_packages.config("/b/routemap", "0.2.0-beta.2", "41")
    assert (cfg["name"], cfg["version"], cfg["prerelease"], cfg["release"]) == (NAME, "0.2.0", "beta.2", "41")
    assert make_packages.config("/b/routemap", "0.2.0", "41").get("prerelease") is None
    dsts = {c["dst"] for c in cfg["contents"]}
    assert {f"/usr/bin/{NAME}", f"/usr/share/applications/{NAME}.desktop", f"/usr/share/pixmaps/{NAME}.png"} <= dsts


def test_the_packages_declare_what_the_build_machine_installs_for_qt():
    build = (ROOT / ".github/workflows/build.yml").read_text()
    for deb in make_packages.LIBS:
        assert re.search(rf"\b{re.escape(deb)}\b", build), deb


def test_every_version_a_person_sees_uses_the_tag_spelling():
    from routemap import __about__
    assert __about__.VERSION == __about__.display_version(__about__.__version__)
    assert __about__.display_version("0.2.0b2") == "0.2.0-beta.2" and __about__.display_version("0.3.0") == "0.3.0"
    assert __about__.VERSION in __about__.version_line() and __about__.VERSION in __about__.USER_AGENT
    build = (ROOT / ".github/workflows/build.yml").read_text()
    assert "import VERSION as v" in build, "release file names use the display spelling"
    for path in ["routemap/cli.py", "routemap/service.py", "routemap/gui/app.py", "routemap/gui/report.py",
                 "routemap/gui/mockup.py"]:
        text = (ROOT / path).read_text()
        assert "__version__" not in text.replace("routemap_engine.__about__ import __version__", ""), path


def test_release_file_names_survive_github():
    """GitHub turned "~" in a release file name into ".", so SHA256SUMS and
    the download page no longer matched the .deb and .rpm (0.2.0-beta.2)."""
    import re
    import release_notes  # noqa: E402
    notes = release_notes.notes("v0.2.0-beta.2")
    names = re.findall(r"routemap[-_][^\s`]*\.(?:deb|rpm|exe|zip|dmg|AppImage|tar\.gz)", notes)
    assert names and all(re.fullmatch(r"[A-Za-z0-9._+*-]+", n) for n in names), names
    script = (ROOT / "packaging/linux/build_packages.sh").read_text()
    assert 'routemap-$version-linux-x86_64.deb' in script and 'routemap-$version-linux-x86_64.rpm' in script
    build = (ROOT / ".github/workflows/build.yml").read_text()
    assert "^[A-Za-z0-9._+-]+$" in build


def test_a_per_machine_install_lives_only_where_ordinary_users_cannot_write():
    """RM-14: per machine, no folder page, Program Files enforced before files
    are copied, and an earlier uninstaller runs elevated only from there; the
    PATH task adds a bin folder with only the CLI launcher. The Windows run of
    install_check.ps1 checks the same on a real machine."""
    iss = (ROOT / "packaging" / "windows" / "routemap.iss").read_text()
    code = iss.split("[Code]", 1)[1]
    flat = " ".join(code.split())
    assert "Result := (PageID = wpSelectDir) and IsAdminInstallMode;" in flat
    assert "if IsAdminInstallMode then WizardForm.DirEdit.Text := MachineDir;" in flat
    assert "if IsAdminInstallMode and not UnderProgramFiles(ExpandConstant('{app}')) then Result :=" in flat
    assert "if IsAdminInstallMode and not UnderProgramFiles(Cmd) then begin" in flat
    adds = re.findall(r"AddToPath\(([^)]*)\)", code.replace("procedure AddToPath(Dir: String)", ""))
    assert adds == ["Bin"], adds
    assert "Bin := ExpandConstant('{app}\\bin');" in flat
    assert "RemoveFromPath(ExpandConstant('{app}\\bin'));" in flat
    check = (ROOT / "packaging" / "windows" / "install_check.ps1").read_text()
    assert "the bin folder holds only" in check and "/DIR=$elsewhere" in check
    assert "does not have the app folder" in check
