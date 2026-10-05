"""Checks that a signed Windows release file is the build run's file plus a
signature from the pinned certificate, and nothing else (RM-04).

    python packaging/windows/signed_check.py exe  BUILT SIGNED --thumbprint SHA1
    python packaging/windows/signed_check.py zip  BUILT.zip SIGNED.zip --thumbprint SHA1
    python packaging/windows/signed_check.py signer SIGNED --thumbprint SHA1

exe: SIGNED's signer certificate has the pinned SHA-1 thumbprint, and with its
signature removed (the certificate table, the security directory entry, the
PE checksum and the 0 to 7 bytes of alignment padding signtool adds) SIGNED is
byte for byte BUILT. zip: the two archives hold the same files, every file is
identical except the .exe files, which must pass the exe check. signer: only
the thumbprint, for the rebuilt installer, whose bytes cannot match the build's.

Whether the signature itself is valid (the digest, the chain to a trusted
root, the timestamp) is osslsigncode verify's job; resign-release.yml runs it
on every signed file before this script. Exit status 0 when all checks pass.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import zipfile


class SignatureCheckError(Exception):
    """The file is not the build's file with the pinned signature."""


def _layout(data: bytes) -> tuple[int, int, int, int]:
    """(checksum offset, security directory offset, certificate table offset, size)."""
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise SignatureCheckError("not a PE file (no MZ header)")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise SignatureCheckError("not a PE file (no PE signature)")
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == 0x10B:
        directories = opt + 96
    elif magic == 0x20B:
        directories = opt + 112
    else:
        raise SignatureCheckError(f"unknown optional header magic {magic:#x}")
    if struct.unpack_from("<I", data, directories - 4)[0] < 5:
        raise SignatureCheckError("no security directory")
    security = directories + 4 * 8
    offset, size = struct.unpack_from("<II", data, security)
    return opt + 64, security, offset, size


def _normalised(data: bytes, checksum: int, security: int) -> bytes:
    out = bytearray(data)
    out[checksum:checksum + 4] = b"\0" * 4
    out[security:security + 8] = b"\0" * 8
    return bytes(out)


def _pkcs7(signed: bytes) -> bytes:
    _, _, offset, size = _layout(signed)
    if not offset or not size:
        raise SignatureCheckError("the file is not signed")
    if offset + size != len(signed):
        raise SignatureCheckError("data follows the certificate table")
    length, revision, kind = struct.unpack_from("<IHH", signed, offset)
    if kind != 2 or length < 8 or length > size:
        raise SignatureCheckError("the certificate table holds no PKCS #7 signature")
    return signed[offset + 8:offset + length]


def same_except_signature(built: bytes, signed: bytes) -> None:
    """Raise unless SIGNED is BUILT plus a signature appended by signtool."""
    checksum, security, offset, size = _layout(signed)
    _pkcs7(signed)
    b_checksum, b_security, b_offset, b_size = _layout(built)
    if (b_checksum, b_security) != (checksum, security):
        raise SignatureCheckError("the headers differ in layout")
    if b_offset or b_size:
        raise SignatureCheckError("the build's file is already signed")
    body = signed[:offset]
    padding = len(body) - len(built)
    if not 0 <= padding < 8 or body[len(built):] != b"\0" * padding:
        raise SignatureCheckError("the signed file is not the build's file plus a signature")
    if _normalised(body[:len(built)], checksum, security) != _normalised(built, checksum, security):
        raise SignatureCheckError("the signed file's bytes differ from the build's")


# ------------------------------------------------------------------- DER ---

def _tlv(data: bytes, pos: int) -> tuple[int, int, int, int]:
    """(tag, start of the whole element, start of its content, end)."""
    tag = data[pos]
    length = data[pos + 1]
    content = pos + 2
    if length & 0x80:
        count = length & 0x7F
        if not 0 < count <= 4:
            raise SignatureCheckError("unsupported DER length")
        length = int.from_bytes(data[content:content + count], "big")
        content += count
    end = content + length
    if end > len(data):
        raise SignatureCheckError("truncated DER")
    return tag, pos, content, end


def _children(data: bytes, content: int, end: int) -> list[tuple[int, int, int, int]]:
    out, pos = [], content
    while pos < end:
        element = _tlv(data, pos)
        out.append(element)
        pos = element[3]
    return out


def signer_thumbprint(signed: bytes) -> str:
    """SHA-1 thumbprint (upper-case hex) of the certificate that signed SIGNED."""
    der = _pkcs7(signed)
    _, _, c, e = _tlv(der, 0)                                  # ContentInfo
    oid, explicit = _children(der, c, e)[:2]
    if der[oid[2]:oid[3]] != bytes.fromhex("2a864886f70d010702"):   # signedData
        raise SignatureCheckError("not PKCS #7 signed data")
    _, _, c, e = _tlv(der, explicit[2])                        # SignedData
    parts = _children(der, c, e)
    certs = next((p for p in parts if p[0] == 0xA0), None)
    infos = parts[-1]
    if certs is None or infos[0] != 0x31:
        raise SignatureCheckError("no certificates or signer in the signature")
    signer = _children(der, infos[2], infos[3])[0]
    fields = _children(der, signer[2], signer[3])
    sid = fields[1]
    if sid[0] != 0x30:
        raise SignatureCheckError("the signer is not named by issuer and serial number")
    issuer, serial = _children(der, sid[2], sid[3])[:2]
    want = (der[issuer[1]:issuer[3]], der[serial[2]:serial[3]])
    for cert in _children(der, certs[2], certs[3]):
        tbs = _children(der, cert[2], cert[3])[0]
        tf = _children(der, tbs[2], tbs[3])
        if tf[0][0] == 0xA0:
            tf = tf[1:]
        if (der[tf[2][1]:tf[2][3]], der[tf[0][2]:tf[0][3]]) == want:
            return hashlib.sha1(der[cert[1]:cert[3]]).hexdigest().upper()
    raise SignatureCheckError("the signer's certificate is not in the signature")


def check_signer(signed: bytes, thumbprint: str) -> None:
    pinned = "".join(thumbprint.split()).upper()
    if len(pinned) != 40 or any(ch not in "0123456789ABCDEF" for ch in pinned):
        raise SignatureCheckError("no pinned certificate thumbprint (packaging/windows/signing-cert-sha1.txt)")
    found = signer_thumbprint(signed)
    if found != pinned:
        raise SignatureCheckError(f"signed by {found}, not by the pinned certificate {pinned}")


def check_exe(built: bytes, signed: bytes, thumbprint: str) -> None:
    check_signer(signed, thumbprint)
    same_except_signature(built, signed)


def check_zip(built_path: str, signed_path: str, thumbprint: str) -> list[str]:
    """Raise unless the signed zip is the built zip with its .exe files signed."""
    with zipfile.ZipFile(built_path) as b, zipfile.ZipFile(signed_path) as s:
        b_names = sorted(i.filename for i in b.infolist() if not i.is_dir())
        s_names = sorted(i.filename for i in s.infolist() if not i.is_dir())
        if b_names != s_names:
            extra = sorted(set(s_names) ^ set(b_names))
            raise SignatureCheckError(f"the archives hold different files: {extra[:5]}")
        report = []
        for name in b_names:
            built, signed = b.read(name), s.read(name)
            if built == signed:
                continue
            if not name.lower().endswith(".exe"):
                raise SignatureCheckError(f"{name} differs from the build's")
            try:
                check_exe(built, signed, thumbprint)
            except SignatureCheckError as exc:
                raise SignatureCheckError(f"{name}: {exc}") from exc
            report.append(f"ok  {name}: the build's bytes, signed by {thumbprint}")
        if not report:
            raise SignatureCheckError("no file in the archive is signed")
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("mode", choices=["exe", "zip", "signer"])
    parser.add_argument("files", nargs="+")
    parser.add_argument("--thumbprint", required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "zip":
            print("\n".join(check_zip(*args.files[:2], args.thumbprint)))
        elif args.mode == "exe":
            built, signed = (open(p, "rb").read() for p in args.files[:2])
            check_exe(built, signed, args.thumbprint)
            print(f"ok  {args.files[1]}: the build's bytes, signed by the pinned certificate")
        else:
            with open(args.files[0], "rb") as handle:
                check_signer(handle.read(), args.thumbprint)
            print(f"ok  {args.files[0]}: signed by the pinned certificate")
    except (SignatureCheckError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"signed_check: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
