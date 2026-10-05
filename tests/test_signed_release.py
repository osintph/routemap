"""A re-signed Windows file is accepted only when it is the build run's file
plus a signature from the pinned certificate (RM-04), and the release
re-signing workflow takes no typed hashes.

The fixtures in tests/fixtures/authenticode are a tiny PE signed with two
throwaway self-signed certificates by osslsigncode (keys not kept).
"""
import io
import pathlib
import struct
import sys
import zipfile

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "authenticode"
sys.path.insert(0, str(ROOT / "packaging" / "windows"))

import signed_check as sc  # noqa: E402

BUILT = (FIX / "built.exe").read_bytes()
SIGNED = (FIX / "signed-pinned.exe").read_bytes()
OTHER = (FIX / "signed-other.exe").read_bytes()
PINNED = (FIX / "pinned.sha1").read_text().strip()


def test_the_builds_file_signed_by_the_pinned_certificate_passes():
    sc.check_exe(BUILT, SIGNED, PINNED)
    sc.check_exe(BUILT, SIGNED, " ".join(PINNED[i:i + 4] for i in range(0, 40, 4)).lower())


def _flip(data, at):
    out = bytearray(data)
    out[at] ^= 0x01
    return bytes(out)


@pytest.mark.parametrize("case", ["other certificate", "changed code", "build differs", "data after the signature",
                                  "unsigned", "no pinned thumbprint", "signed build"])
def test_anything_else_is_refused(case):
    built, signed, pin = BUILT, SIGNED, PINNED
    if case == "other certificate":
        signed = OTHER
    elif case == "changed code":
        signed = _flip(SIGNED, 0x200)                 # first byte of .text
    elif case == "build differs":
        built = _flip(BUILT, 0x300)
    elif case == "data after the signature":
        signed = SIGNED + b"\0" * 8
    elif case == "unsigned":
        signed = BUILT
    elif case == "no pinned thumbprint":
        pin = "unset"
    elif case == "signed build":
        built = SIGNED
    with pytest.raises(sc.SignatureCheckError):
        sc.check_exe(built, signed, pin)


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_a_signed_zip_must_be_the_builds_zip_with_its_exes_signed(tmp_path):
    built = {"Route Map/routemap.exe": BUILT, "Route Map/python312.dll": b"dll", "Route Map/LICENSE": b"agpl"}
    good = dict(built, **{"Route Map/routemap.exe": SIGNED})
    (tmp_path / "b.zip").write_bytes(_zip(built))
    (tmp_path / "s.zip").write_bytes(_zip(good))
    assert sc.check_zip(str(tmp_path / "b.zip"), str(tmp_path / "s.zip"), PINNED)
    for bad in (dict(good, **{"Route Map/python312.dll": b"evil"}),      # another file changed
                dict(good, **{"Route Map/extra.dll": b"x"}),              # a file added
                dict(good, **{"Route Map/routemap.exe": OTHER}),          # someone else's signature
                built):                                                   # nothing signed
        (tmp_path / "s.zip").write_bytes(_zip(bad))
        with pytest.raises(sc.SignatureCheckError):
            sc.check_zip(str(tmp_path / "b.zip"), str(tmp_path / "s.zip"), PINNED)


def test_the_signer_of_a_rebuilt_installer_is_checked():
    sc.check_signer(SIGNED, PINNED)
    with pytest.raises(sc.SignatureCheckError):
        sc.check_signer(OTHER, PINNED)
    with pytest.raises(sc.SignatureCheckError):
        sc.check_signer(BUILT, PINNED)


def test_a_pe32_layout_is_read_too():
    pe = bytearray(BUILT)
    struct.pack_into("<H", pe, 0x80 + 24, 0x10B)       # claim PE32: directories move up 16 bytes
    struct.pack_into("<I", pe, 0x80 + 24 + 92, 16)     # and PE32's NumberOfRvaAndSizes
    checksum, security, *_ = sc._layout(bytes(pe))
    assert (checksum, security) == (0x80 + 24 + 64, 0x80 + 24 + 96 + 32)


def test_resign_release_takes_no_typed_hashes_and_checks_every_windows_file():
    wf = ROOT / ".github" / "workflows" / "resign-release.yml"
    doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
    inputs = doc[True]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"tag", "build_run"}, inputs
    text = wf.read_text(encoding="utf-8")
    assert "osslsigncode verify" in text
    assert "signed_check.py zip" in text and "signed_check.py signer" in text
    assert "signing-cert-sha1.txt" in text


def test_the_pinned_thumbprint_is_absent_or_a_thumbprint_and_absent_refuses_every_signature():
    """No Certum certificate yet: the file is absent, and an empty pin refuses."""
    pin = ROOT / "packaging" / "windows" / "signing-cert-sha1.txt"
    if pin.exists():
        value = pin.read_text().splitlines()[0].strip()
        assert len(value) == 40 and all(c in "0123456789ABCDEF" for c in value), value
    for empty in ("", " ", "unset"):
        with pytest.raises(sc.SignatureCheckError, match="no pinned certificate"):
            sc.check_signer(b"MZ", empty)
