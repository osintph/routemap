"""
In-app update: download the release file for this system, check it, hand it over.

Qt-free; the GUI drives it from a worker and shows each step.

WHAT IS CHECKED, IN ORDER
-------------------------
1. SHA256SUMS.ed25519 is a valid Ed25519 signature, by a key embedded in this
   build (routemap/updatekey.py), over the bytes ``"<NAME> <tag>\\n"`` followed
   by SHA256SUMS exactly as published. Binding the tag means a genuine older
   SHA256SUMS cannot be passed off as a newer release.
2. SHA256SUMS lists the file exactly once.
3. The downloaded file's SHA-256 is the one listed.

Any failed check deletes everything downloaded and raises UpdateFailed naming
the check. SHA256SUMS.asc (GPG) is untouched and still the signature people
check by hand.

WHERE THE TRAFFIC GOES
----------------------
Only to this repository's release files on github.com (service.release_url),
and to the one place GitHub redirects a release download to,
release-assets.githubusercontent.com. Any other redirect, any http URL, and
any answer larger than its cap stop the download. Nothing else is contacted.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import re
import shutil
import stat
import sys
import tempfile
import threading
from typing import Callable
from urllib.parse import urlsplit

from routemap import service
from routemap.__about__ import NAME
from routemap.updatekey import UPDATE_KEYS

SUMS = "SHA256SUMS"
SIGNATURE = "SHA256SUMS.ed25519"
ASSET_HOST = "release-assets.githubusercontent.com"
MAX_SUMS_BYTES = 64 * 1024
MAX_SIGNATURE_BYTES = 64
MAX_FILE_BYTES = 600 * 1024 * 1024
CHUNK = 256 * 1024

STEP_DOWNLOAD = "download"
STEP_SIGNATURE = "signature"
STEP_LISTED = "listed"
STEP_HASH = "hash"
STEP_INSTALL = "install"

LINE = re.compile(r"^([0-9a-f]{64}) [ *](.+)$")


class UpdateFailed(Exception):
    """One check or step failed. ``step`` names it; the message says why."""

    def __init__(self, step: str, message: str):
        super().__init__(message)
        self.step = step
        self.message = message


def available(latest: dict | None) -> bool:
    """Whether this build can update in place from *latest*: it has a key and
    the release publishes the signature file."""
    return bool(UPDATE_KEYS) and bool(latest) and SIGNATURE in (latest.get("assets") or {}) \
        and SUMS in (latest.get("assets") or {})


def signed_message(tag: str, sums: bytes) -> bytes:
    return f"{NAME} {tag}\n".encode("ascii") + sums


def signature_ok(tag: str, sums: bytes, signature: bytes, keys=None) -> bool:
    """True when *signature* is a valid Ed25519 signature over the release
    message by one of *keys* (raw 32-byte public keys)."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if len(signature) != 64:
        return False
    message = signed_message(tag, sums)
    for raw in UPDATE_KEYS if keys is None else keys:
        try:
            Ed25519PublicKey.from_public_bytes(raw).verify(signature, message)
            return True
        except (InvalidSignature, ValueError):
            continue
    return False


def listed_digest(sums: bytes, name: str) -> str:
    """The SHA-256 SHA256SUMS lists for *name*. Raises UpdateFailed unless the
    name appears exactly once on a well-formed line."""
    try:
        text = sums.decode("ascii")
    except UnicodeDecodeError:
        raise UpdateFailed(STEP_LISTED, "SHA256SUMS is not plain text.") from None
    found = []
    for line in text.splitlines():
        m = LINE.match(line)
        if m and m.group(2) == name:
            found.append(m.group(1))
    if len(found) != 1:
        raise UpdateFailed(STEP_LISTED, f"SHA256SUMS lists {name} {len(found)} times, not once.")
    return found[0]


def _allowed(url: str, first: bool) -> bool:
    if first:
        return service.release_url(url) is not None and "/releases/download/" in url
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.netloc == ASSET_HOST


def fetch(url: str, dest: pathlib.Path, limit: int,
          on_bytes: Callable[[int, int | None], None] | None = None,
          cancel: threading.Event | None = None, *, transport=None) -> str:
    """Download *url* to *dest*, at most *limit* bytes, following only the
    GitHub release redirect. Returns the SHA-256 of what was written."""
    import httpx

    if not _allowed(url, first=True):
        raise UpdateFailed(STEP_DOWNLOAD, "The download address is not one of this project's releases.")
    digest = hashlib.sha256()
    kwargs = {"timeout": 30.0, "follow_redirects": False,
              "headers": {"User-Agent": service.user_agent()}}
    if transport is not None:
        kwargs["transport"] = transport
    with httpx.Client(**kwargs) as client:
        current, hops = url, 0
        while True:
            with client.stream("GET", current) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    target = response.headers.get("location", "")
                    hops += 1
                    if hops > 1 or not _allowed(target, first=False):
                        raise UpdateFailed(STEP_DOWNLOAD, "GitHub sent the download somewhere "
                                                          "unexpected, so nothing was downloaded.")
                    current = target
                    continue
                if response.status_code != 200:
                    raise UpdateFailed(STEP_DOWNLOAD, f"GitHub answered HTTP {response.status_code}.")
                size = response.headers.get("content-length")
                total = int(size) if size and size.isdigit() else None
                if total is not None and total > limit:
                    raise UpdateFailed(STEP_DOWNLOAD, "The file is larger than any release file should be.")
                written = 0
                with open(dest, "wb") as out:
                    for chunk in response.iter_bytes(CHUNK):
                        if cancel is not None and cancel.is_set():
                            raise UpdateFailed(STEP_DOWNLOAD, "Cancelled.")
                        written += len(chunk)
                        if written > limit:
                            raise UpdateFailed(STEP_DOWNLOAD, "The file is larger than any release file should be.")
                        out.write(chunk)
                        digest.update(chunk)
                        if on_bytes is not None:
                            on_bytes(written, total)
                return digest.hexdigest()


def private_dir() -> pathlib.Path:
    """A fresh folder only this user can read, for one update."""
    path = pathlib.Path(tempfile.mkdtemp(prefix=f"{NAME}-update-"))
    os.chmod(path, stat.S_IRWXU)
    return path


def download_and_verify(latest: dict, name: str, workdir: pathlib.Path,
                        on_step: Callable[[str, str], None] | None = None,
                        on_bytes: Callable[[int, int | None], None] | None = None,
                        cancel: threading.Event | None = None, *, keys=None, transport=None) -> pathlib.Path:
    """Fetch SHA256SUMS, its signature and *name* from *latest* into *workdir*,
    run the three checks, return the verified file. On any failure every file
    in *workdir* is deleted before UpdateFailed propagates."""
    step = on_step or (lambda s, state: None)
    assets = latest.get("assets") or {}
    tag = latest["tag"]
    try:
        step(STEP_DOWNLOAD, "running")
        sums_path, sig_path, file_path = workdir / SUMS, workdir / SIGNATURE, workdir / name
        fetch(assets[SUMS], sums_path, MAX_SUMS_BYTES, cancel=cancel, transport=transport)
        fetch(assets[SIGNATURE], sig_path, MAX_SIGNATURE_BYTES, cancel=cancel, transport=transport)
        actual = fetch(assets[name], file_path, MAX_FILE_BYTES, on_bytes, cancel, transport=transport)
        step(STEP_DOWNLOAD, "ok")

        step(STEP_SIGNATURE, "running")
        sums = sums_path.read_bytes()
        if not signature_ok(tag, sums, sig_path.read_bytes(), keys):
            raise UpdateFailed(STEP_SIGNATURE, f"The signature on SHA256SUMS is not by the {NAME} "
                                               f"update key for {tag}.")
        step(STEP_SIGNATURE, "ok")

        step(STEP_HASH, "running")
        expected = listed_digest(sums, name)
        if actual != expected:
            raise UpdateFailed(STEP_HASH, "The downloaded file's SHA-256 is not the one SHA256SUMS lists.")
        step(STEP_HASH, "ok")
        return file_path
    except UpdateFailed as exc:
        step(exc.step if exc.step != STEP_LISTED else STEP_HASH, "failed")
        discard(workdir)
        raise
    except KeyError as exc:
        discard(workdir)
        raise UpdateFailed(STEP_DOWNLOAD, f"The release has no {exc.args[0]}.") from None
    except Exception as exc:  # noqa: BLE001 - network or disk: still a failed download
        discard(workdir)
        raise UpdateFailed(STEP_DOWNLOAD, f"The download failed ({type(exc).__name__}).") from None


def discard(workdir: pathlib.Path) -> None:
    shutil.rmtree(workdir, ignore_errors=True)


# ------------------------------------------------------------------ hand-over --

def plan(path: pathlib.Path, system: str | None = None, appimage: str | None = None) -> dict:
    """What to do with a verified file: {"kind", "argv", "text"}.

    kind is "installer" (Windows: run it, then quit), "open" (macOS DMG, Linux
    .deb or .rpm: the system's own installer takes over) or "replace" (an
    AppImage that is running: swap the file, restart)."""
    system = system or sys.platform
    name = path.name
    if system.startswith("win") and name.endswith("-setup.exe"):
        return {"kind": "installer", "argv": [str(path)],
                "text": f"Verified. {NAME} closes and the installer starts."}
    if system == "darwin" and name.endswith(".dmg"):
        return {"kind": "open", "argv": ["open", str(path)],
                "text": "Verified. The disk image opens in Finder: drag Route Map to Applications."}
    if system.startswith("linux") and name.endswith(".AppImage") and appimage:
        return {"kind": "replace", "argv": [appimage],
                "text": f"Verified. {NAME} replaces this AppImage with the new one and restarts."}
    if system.startswith("linux") and name.endswith((".deb", ".rpm")):
        return {"kind": "open", "argv": ["xdg-open", str(path)],
                "text": "Verified. The package opens in your system's software installer."}
    return {"kind": "open", "argv": [], "text": f"Verified. The file is at {path}."}


def replace_appimage(new: pathlib.Path, running: str) -> None:
    """Swap the running AppImage for *new* in one rename, in its own folder."""
    target = pathlib.Path(running)
    staged = target.with_name(f".{target.name}.update")
    try:
        shutil.copyfile(new, staged)
        os.chmod(staged, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        with open(staged, "rb") as f:
            os.fsync(f.fileno())
        os.replace(staged, target)
    except OSError as exc:
        try:
            staged.unlink()
        except OSError:
            pass
        raise UpdateFailed(STEP_INSTALL, f"The AppImage could not be replaced: {exc.strerror or exc}. "
                                         "The folder may not be writable.") from None
