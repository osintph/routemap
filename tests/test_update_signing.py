"""CI's signing and checking scripts and the app agree.

Runs packaging/sign_update.sh with a throwaway key and OpenSSL 3, then checks
the result with routemap.updater (what the app runs) and with
packaging/verify_update_signature.sh (what CI runs before publishing): both
accept the genuine signature and both refuse another key, another tag and a
changed file. Skipped where no OpenSSL 3 is found (macOS ships LibreSSL);
CI's Ubuntu has it.
"""
import base64
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from routemap import updater

ROOT = pathlib.Path(__file__).resolve().parents[1]
TAG = "v0.2.0-beta.6"


def _openssl3():
    for cand in (os.environ.get("OPENSSL"), shutil.which("openssl"), "/opt/homebrew/opt/openssl@3/bin/openssl",
                 "/usr/local/opt/openssl@3/bin/openssl"):
        if cand and os.path.exists(cand):
            out = subprocess.run([cand, "version"], capture_output=True, text=True).stdout
            if out.startswith("OpenSSL 3"):
                return cand
    return None


OPENSSL = _openssl3()
pytestmark = [pytest.mark.skipif(OPENSSL is None, reason="needs OpenSSL 3"),
              pytest.mark.skipif(sys.platform == "win32", reason="bash script")]


def _release(tmp_path):
    folder = tmp_path / "release"
    folder.mkdir()
    names = ["routemap-0.2.0-beta.6-linux-x86_64.AppImage", "routemap-0.2.0-beta.6-macos-arm64.dmg"]
    lines = []
    for n in names:
        (folder / n).write_bytes(n.encode() * 50)
        lines.append(f"{hashlib.sha256((folder / n).read_bytes()).hexdigest()}  {n}\n")
    (folder / "SHA256SUMS").write_text("".join(lines))
    return folder


def _key():
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return pem, raw


def _sign(folder, pem, tmp_path, tag=TAG):
    env = dict(os.environ, UPDATE_ED25519_KEY=pem, OPENSSL=OPENSSL, RUNNER_TEMP=str(tmp_path / "runner"))
    (tmp_path / "runner").mkdir(exist_ok=True)
    return subprocess.run(["bash", str(ROOT / "packaging" / "sign_update.sh"), tag, str(folder)],
                          env=env, capture_output=True, text=True)


def _verify_sh(folder, tag, keys, tmp_path):
    env = dict(os.environ, OPENSSL=OPENSSL, RUNNER_TEMP=str(tmp_path / "runner"),
               UPDATE_PUBLIC_KEYS_B64=" ".join(base64.b64encode(k).decode() for k in keys))
    (tmp_path / "runner").mkdir(exist_ok=True)
    return subprocess.run(["bash", str(ROOT / "packaging" / "verify_update_signature.sh"), tag, str(folder)],
                          env=env, capture_output=True, text=True)


def test_what_ci_signs_the_app_and_ci_accept(tmp_path):
    folder, (pem, raw) = _release(tmp_path), _key()
    result = _sign(folder, pem, tmp_path)
    assert result.returncode == 0, result.stderr
    sig = (folder / "SHA256SUMS.ed25519").read_bytes()
    assert updater.signature_ok(TAG, (folder / "SHA256SUMS").read_bytes(), sig, (raw,))
    check = _verify_sh(folder, TAG, (raw,), tmp_path)
    assert check.returncode == 0, check.stdout + check.stderr


def test_the_key_never_outlives_the_script(tmp_path):
    folder, (pem, _) = _release(tmp_path), _key()
    _sign(folder, pem, tmp_path)
    leftovers = list((tmp_path / "runner").iterdir())
    assert leftovers == [], leftovers
    assert pem.splitlines()[1] not in (folder / "SHA256SUMS.ed25519").read_bytes().decode("latin-1")


def test_a_failed_signing_also_removes_the_key(tmp_path):
    folder, (pem, _) = _release(tmp_path), _key()
    env_pem = pem.replace("PRIVATE KEY-----\n", "PRIVATE KEY-----\nAAAA", 1)   # unreadable key
    result = _sign(folder, env_pem, tmp_path)
    assert result.returncode != 0
    assert list((tmp_path / "runner").iterdir()) == []


def test_no_key_means_no_release(tmp_path):
    folder = _release(tmp_path)
    result = _sign(folder, "", tmp_path)
    assert result.returncode != 0 and "UPDATE_ED25519_KEY" in result.stdout + result.stderr


def test_ci_and_the_app_refuse_the_same_signatures(tmp_path):
    folder, (pem, raw) = _release(tmp_path), _key()
    assert _sign(folder, pem, tmp_path).returncode == 0
    sums, sig = (folder / "SHA256SUMS").read_bytes(), (folder / "SHA256SUMS.ed25519").read_bytes()
    other = _key()[1]
    for tag, keys in (("v0.2.0-beta.5", (raw,)), (TAG, (other,))):
        assert not updater.signature_ok(tag, sums, sig, keys)
        assert _verify_sh(folder, tag, keys, tmp_path).returncode == 1
    # one rotated-out key and the real one: both accept
    assert updater.signature_ok(TAG, sums, sig, (other, raw))
    assert _verify_sh(folder, TAG, (other, raw), tmp_path).returncode == 0


def test_ci_refuses_a_file_that_does_not_match_sha256sums(tmp_path):
    folder, (pem, raw) = _release(tmp_path), _key()
    assert _sign(folder, pem, tmp_path).returncode == 0
    victim = next(p for p in folder.iterdir() if p.name.endswith(".dmg"))
    victim.write_bytes(victim.read_bytes() + b"x")
    assert _verify_sh(folder, TAG, (raw,), tmp_path).returncode == 1


def test_ci_reads_the_keys_routemap_embeds(tmp_path, monkeypatch):
    """With no override, the script reads _KEYS_B64 from routemap/updatekey.py;
    today that is empty, so it must refuse rather than pass."""
    folder, (pem, _) = _release(tmp_path), _key()
    assert _sign(folder, pem, tmp_path).returncode == 0
    env = {k: v for k, v in os.environ.items() if k != "UPDATE_PUBLIC_KEYS_B64"}
    env.update(OPENSSL=OPENSSL, RUNNER_TEMP=str(tmp_path / "runner"))
    from routemap.updatekey import UPDATE_KEYS
    result = subprocess.run(["bash", str(ROOT / "packaging" / "verify_update_signature.sh"), TAG, str(folder)],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 1   # a throwaway key is never an embedded one
    if not UPDATE_KEYS:
        assert "embeds no update key" in result.stdout + result.stderr
