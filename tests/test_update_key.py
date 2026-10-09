"""The embedded update key is the one the README publishes, and it is a valid Ed25519 key."""
import base64
import pathlib
import re

from cryptography.hazmat.primitives import serialization

from routemap import updatekey

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_the_build_embeds_exactly_one_valid_key():
    assert len(updatekey.UPDATE_KEYS) == 1 and len(updatekey.UPDATE_KEYS[0]) == 32


def test_the_readme_publishes_the_same_key():
    pem = re.search(r"-----BEGIN PUBLIC KEY-----\n(.+?)\n-----END PUBLIC KEY-----",
                    (ROOT / "README.md").read_text(), re.S)
    key = serialization.load_pem_public_key(pem.group(0).encode())
    raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    assert raw == updatekey.UPDATE_KEYS[0]
    assert base64.b64decode(pem.group(1))[12:] == raw
