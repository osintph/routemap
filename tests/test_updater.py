"""The in-app update: every tampering is refused, and refusing leaves nothing behind.

Generalised over the class of attack, not one instance: a changed file, a
changed SHA256SUMS, a signature by another key, a genuine signature from an
older release, an ambiguous listing, a redirect off GitHub, an oversize answer
and an address outside this repository's releases. Each must fail at its own
step and delete everything downloaded.
"""
import hashlib
import pathlib

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from routemap import updater
from routemap.__about__ import NAME, REPO_URL

TAG = "v0.2.0-beta.6"
FILE = "routemap-0.2.0-beta.6-linux-x86_64.AppImage"
BASE = f"{REPO_URL}/releases/download/{TAG}"
CDN = f"https://{updater.ASSET_HOST}/github-production-release-asset/1/"


def _raw(public):
    return public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


class Release:
    def __init__(self, payload=b"new build\n" * 1000, tag=TAG, key=None):
        self.key = key or Ed25519PrivateKey.generate()
        self.payload = payload
        self.sums = (f"{hashlib.sha256(payload).hexdigest()}  {FILE}\n"
                     f"{'0' * 64}  routemap-0.2.0-beta.6-linux-x86_64.deb\n").encode()
        self.signature = self.key.sign(updater.signed_message(tag, self.sums))
        self.redirect = {}
        self.extra_hops = 0

    @property
    def keys(self):
        return (_raw(self.key.public_key()),)

    def latest(self):
        names = [updater.SUMS, updater.SIGNATURE, FILE]
        return {"tag": TAG, "assets": {n: f"{BASE}/{n}" for n in names}}

    def transport(self):
        bodies = {updater.SUMS: lambda: self.sums, updater.SIGNATURE: lambda: self.signature,
                  FILE: lambda: self.payload}

        def handler(request: httpx.Request):
            url = str(request.url)
            if url.startswith(BASE + "/"):
                name = url.rsplit("/", 1)[1]
                where = self.redirect.get(name, CDN + name)
                return httpx.Response(302, headers={"location": where})
            if url.startswith(CDN):
                name = url[len(CDN):]
                if self.extra_hops:
                    return httpx.Response(302, headers={"location": CDN + name})
                return httpx.Response(200, content=bodies[name]())
            return httpx.Response(404)

        return httpx.MockTransport(handler)


def _run(rel, tmp_path, **kw):
    work = tmp_path / "work"
    work.mkdir()
    steps = []
    try:
        path = updater.download_and_verify(rel.latest(), FILE, work, on_step=lambda s, st: steps.append((s, st)),
                                           keys=kw.pop("keys", rel.keys), transport=rel.transport())
        return path, steps, work
    except updater.UpdateFailed as exc:
        return exc, steps, work


def test_a_genuine_release_verifies(tmp_path):
    rel = Release()
    path, steps, _ = _run(rel, tmp_path)
    assert isinstance(path, pathlib.Path) and path.read_bytes() == rel.payload
    assert [s for s, st in steps if st == "ok"] == ["download", "signature", "hash"]


def _assert_refused(result, work, step):
    exc, steps, _ = result
    assert isinstance(exc, updater.UpdateFailed), exc
    assert exc.step == step, (exc.step, exc.message)
    assert not work.exists() or not any(work.iterdir()), list(work.iterdir())
    assert (step if step != "listed" else "hash", "failed") in steps, steps


def test_a_changed_file_is_refused_and_deleted(tmp_path):
    rel = Release()
    rel.payload = rel.payload[:-1] + b"X"
    result = _run(rel, tmp_path)
    _assert_refused(result, result[2], "hash")


def test_a_changed_sums_file_is_refused(tmp_path):
    rel = Release()
    rel.sums = rel.sums.replace(b"  routemap", b"  routemap", 1) + b"\n"
    result = _run(rel, tmp_path)
    _assert_refused(result, result[2], "signature")


def test_a_signature_by_another_key_is_refused(tmp_path):
    rel = Release()
    other = (_raw(Ed25519PrivateKey.generate().public_key()),)
    result = _run(rel, tmp_path, keys=other)
    _assert_refused(result, result[2], "signature")


def test_an_older_releases_genuine_signature_is_refused(tmp_path):
    rel = Release()
    rel.signature = rel.key.sign(updater.signed_message("v0.2.0-beta.5", rel.sums))
    result = _run(rel, tmp_path)
    _assert_refused(result, result[2], "signature")


def test_a_truncated_signature_is_refused(tmp_path):
    rel = Release()
    rel.signature = rel.signature[:63]
    result = _run(rel, tmp_path)
    _assert_refused(result, result[2], "signature")


@pytest.mark.parametrize("sums", [b"", b"not a sums file\n", None])
def test_a_file_not_listed_exactly_once_is_refused(tmp_path, sums):
    rel = Release()
    line = f"{hashlib.sha256(rel.payload).hexdigest()}  {FILE}\n".encode()
    rel.sums = (line + line) if sums is None else sums
    rel.signature = rel.key.sign(updater.signed_message(TAG, rel.sums))
    result = _run(rel, tmp_path)
    _assert_refused(result, result[2], "listed")


@pytest.mark.parametrize("where", ["https://evil.example/x", f"http://{updater.ASSET_HOST}/x",
                                   "https://github.com/someone/else/releases/download/x",
                                   f"https://{updater.ASSET_HOST}.evil.example/x", ""])
def test_a_redirect_off_githubs_asset_host_is_refused(tmp_path, where):
    rel = Release()
    rel.redirect[FILE] = where
    result = _run(rel, tmp_path)
    _assert_refused(result, result[2], "download")


def test_a_second_redirect_is_refused(tmp_path):
    rel = Release()
    rel.extra_hops = 1
    result = _run(rel, tmp_path)
    _assert_refused(result, result[2], "download")


def test_an_oversize_answer_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "MAX_FILE_BYTES", 100)
    result = _run(Release(), tmp_path)
    _assert_refused(result, result[2], "download")


@pytest.mark.parametrize("url", ["https://example.com/routemap.AppImage",
                                 "http://github.com/osintph/routemap/releases/download/x",
                                 "https://github.com/osintph/routemap/releases/download/../../x",
                                 "https://github.com/osintph/other/releases/download/v1/x"])
def test_only_this_repositorys_release_files_are_fetched(tmp_path, url):
    with pytest.raises(updater.UpdateFailed) as exc:
        updater.fetch(url, tmp_path / "x", 10, transport=Release().transport())
    assert exc.value.step == "download" and not (tmp_path / "x").exists()


def test_no_key_in_the_build_means_no_in_app_update(monkeypatch):
    rel = Release()
    monkeypatch.setattr(updater, "UPDATE_KEYS", ())
    assert not updater.available(rel.latest())
    monkeypatch.setattr(updater, "UPDATE_KEYS", rel.keys)
    assert updater.available(rel.latest())
    assert not updater.available({"tag": TAG, "assets": {updater.SUMS: "x"}})


def test_the_signed_message_names_the_product_and_the_tag():
    assert updater.signed_message(TAG, b"abc") == f"{NAME} {TAG}\n".encode() + b"abc"


@pytest.mark.parametrize("name,system,appimage,kind", [
    ("routemap-0.2.0-beta.6-windows-x86_64-setup.exe", "win32", None, "installer"),
    ("routemap-0.2.0-beta.6-macos-arm64.dmg", "darwin", None, "open"),
    ("routemap-0.2.0-beta.6-macos-x86_64.dmg", "darwin", None, "open"),
    ("routemap-0.2.0-beta.6-linux-x86_64.deb", "linux", None, "open"),
    ("routemap-0.2.0-beta.6-linux-x86_64.rpm", "linux", None, "open"),
    ("routemap-0.2.0-beta.6-linux-x86_64.AppImage", "linux", "/home/u/Apps/routemap.AppImage", "replace"),
])
def test_each_platform_hands_the_verified_file_to_the_right_place(name, system, appimage, kind):
    p = updater.plan(pathlib.Path("/tmp/x") / name, system, appimage)
    assert p["kind"] == kind
    assert chr(0x2014) not in p["text"]


def test_an_appimage_is_replaced_in_one_rename(tmp_path):
    running = tmp_path / "routemap.AppImage"
    running.write_bytes(b"old")
    new = tmp_path / "new.AppImage"
    new.write_bytes(b"new")
    updater.replace_appimage(new, str(running))
    assert running.read_bytes() == b"new" and running.stat().st_mode & 0o111
    assert not any(p.name.endswith(".update") for p in tmp_path.iterdir())


def test_a_failed_appimage_replacement_leaves_the_old_one(tmp_path, monkeypatch):
    running = tmp_path / "routemap.AppImage"
    running.write_bytes(b"old")
    new = tmp_path / "new.AppImage"
    new.write_bytes(b"new")

    def boom(*a, **k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(updater.os, "replace", boom)
    with pytest.raises(updater.UpdateFailed) as exc:
        updater.replace_appimage(new, str(running))
    assert exc.value.step == "install" and running.read_bytes() == b"old"
    assert not any(p.name.endswith(".update") for p in tmp_path.iterdir())
