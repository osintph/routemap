"""
The public keys that sign a release's SHA256SUMS for the in-app update.

Raw 32-byte Ed25519 public keys. The private key is held only in the
repository's "downloads" environment, where the release workflow signs
"<NAME> <tag>\n" + SHA256SUMS into SHA256SUMS.ed25519 (routemap/updater.py
says what is checked). A tuple, so a rotation ships the new key beside the old
one for one release.

A build with no key here does not offer the in-app update, and Check for
Updates opens the download in the browser instead.

The key below, created 2026-10-09. As PEM:

    -----BEGIN PUBLIC KEY-----
    MCowBQYDK2VwAyEALvKv5pMRnHidP2qzX+j24fSKbNUiCJuqWfx9aYbkha4=
    -----END PUBLIC KEY-----

SHA-256 of the raw 32 bytes:
87d846cb35e80467478f33f1b4de2ed71409134264c2b83216c27b571dbac4a5
"""
import base64

_KEYS_B64: tuple[str, ...] = (
    "LvKv5pMRnHidP2qzX+j24fSKbNUiCJuqWfx9aYbkha4=",
)

UPDATE_KEYS: tuple[bytes, ...] = tuple(base64.b64decode(k) for k in _KEYS_B64)
