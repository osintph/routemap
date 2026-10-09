"""
The public keys that sign a release's SHA256SUMS for the in-app update.

Raw 32-byte Ed25519 public keys. The private key is held only in the
repository's "downloads" environment, where the release workflow signs
"<NAME> <tag>\n" + SHA256SUMS into SHA256SUMS.ed25519 (routemap/updater.py
says what is checked). A tuple, so a rotation ships the new key beside the old
one for one release.

Empty until the key is created: the in-app update is then not offered, and
Check for Updates opens the download in the browser as before.
"""
import base64

_KEYS_B64: tuple[str, ...] = ()

UPDATE_KEYS: tuple[bytes, ...] = tuple(base64.b64decode(k) for k in _KEYS_B64)
