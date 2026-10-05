"""Check for Updates offers the release file for this machine."""
from routemap import service

TAG = "v0.2.0-beta.2"
V = "0.2.0-beta.2"
BASE = f"https://github.com/osintph/routemap/releases/download/{TAG}/"
ASSETS = {name: BASE + name for name in [
    f"routemap-{V}-macos-arm64.dmg", f"routemap-{V}-macos-x86_64.dmg",
    f"routemap-{V}-windows-x86_64-setup.exe", f"routemap-{V}-windows-x86_64.zip",
    f"routemap-{V}-linux-x86_64.AppImage", f"routemap-{V}-linux-x86_64.tar.gz",
    f"routemap-{V}-linux-x86_64.deb", f"routemap-{V}-linux-x86_64.rpm",
    "SHA256SUMS", "SHA256SUMS.asc"]}


def pick(**kw):
    found = service.installer_for(ASSETS, **kw)
    return found[0] if found else None


def test_each_platform_gets_its_installer():
    assert pick(system="win32", machine="AMD64") == f"routemap-{V}-windows-x86_64-setup.exe"
    assert pick(system="darwin", machine="arm64") == f"routemap-{V}-macos-arm64.dmg"
    assert pick(system="darwin", machine="x86_64") == f"routemap-{V}-macos-x86_64.dmg"
    assert pick(system="linux", machine="x86_64", family="deb", appimage=False) == f"routemap-{V}-linux-x86_64.deb"
    assert pick(system="linux", machine="x86_64", family="rpm", appimage=False) == f"routemap-{V}-linux-x86_64.rpm"
    nfpm_style = {"routemap_0.2.0~beta.1-9_amd64.deb": "d", "routemap-0.2.0~beta.1-9.x86_64.rpm": "r"}
    assert service.installer_for(nfpm_style, system="linux", family="deb", appimage=False)[1] == "d"
    assert pick(system="linux", machine="x86_64", family="", appimage=False).endswith(".AppImage")
    assert pick(system="linux", machine="x86_64", family="deb", appimage=True).endswith(".AppImage")
    assert service.installer_for(ASSETS, system="win32")[1] == BASE + f"routemap-{V}-windows-x86_64-setup.exe"


def test_an_older_release_without_an_installer_offers_what_it_has():
    old = {"routemap-0.2.0b1-windows-x86_64.zip": "z", "routemap-0.2.0b1-linux-x86_64.AppImage": "a"}
    assert service.installer_for(old, system="win32", machine="AMD64") == ("routemap-0.2.0b1-windows-x86_64.zip", "z")
    assert service.installer_for(old, system="linux", machine="x86_64", family="deb", appimage=False)[1] == "a"
    assert service.installer_for({}, system="darwin", machine="arm64") is None


def test_linux_family_from_os_release():
    assert service.linux_family('ID=ubuntu\nID_LIKE=debian\n') == "deb"
    assert service.linux_family('ID="linuxmint"\nID_LIKE="ubuntu debian"\n') == "deb"
    assert service.linux_family('ID=fedora\n') == "rpm"
    assert service.linux_family('ID="rocky"\nID_LIKE="rhel centos fedora"\n') == "rpm"
    assert service.linux_family('ID=opensuse-tumbleweed\nID_LIKE="opensuse suse"\n') == "rpm"
    assert service.linux_family('ID=arch\n') == ""


def test_versions_compare_across_both_spellings():
    o = service.release_order
    assert o("v0.2.0-beta.2") == o("0.2.0b2") == o("v0.2.0b2")
    assert o("v0.2.0-beta.1") < o("v0.2.0-beta.2") < o("v0.2.0-rc.1") < o("v0.2.0") < o("v0.2.1")
    assert o("v0.1.0-beta.5") < o("v0.2.0-beta.1")
    assert o("nonsense") == ()
