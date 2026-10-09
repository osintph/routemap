#!/bin/bash
# Checks SHA256SUMS.ed25519 the way the app will, before a release is published.
#
#   packaging/verify_update_signature.sh <tag> <release-dir>
#
# With OpenSSL 3 and the public keys routemap/updatekey.py embeds, so a
# signature by any other key, or over anything but "<NAME> <tag>\n" and this
# SHA256SUMS, fails the release instead of every user's update. Installs
# nothing: the release job sees secrets, and such jobs install no packages.
# tests/test_update_signing.py checks that this script and routemap/updater.py
# accept and refuse the same signatures. UPDATE_PUBLIC_KEYS_B64 (space
# separated) replaces the embedded keys; the tests use it, CI does not.
set -euo pipefail
TAG="$1"
DIR="$2"
OPENSSL="${OPENSSL:-openssl}"
cd "$(dirname "$0")/.."
NAME="$(sed -n 's/^NAME = "\([a-z0-9-]*\)"$/\1/p' routemap/__about__.py)"
[ -n "$NAME" ] || { echo "::error::NAME not found in routemap/__about__.py"; exit 1; }
if [ -n "${UPDATE_PUBLIC_KEYS_B64:-}" ]; then
  KEYS="$UPDATE_PUBLIC_KEYS_B64"
else
  # The base64 strings inside _KEYS_B64 = ( ... ) in routemap/updatekey.py.
  KEYS="$(sed -n '/^_KEYS_B64/,/)/p' routemap/updatekey.py | grep -oE '"[A-Za-z0-9+/=]{44}"' | tr -d '"' | tr '\n' ' ' || true)"
fi
[ -n "${KEYS// /}" ] || { echo "::error::routemap/updatekey.py embeds no update key"; exit 1; }
WORK="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/routemap-update-verify.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
{ printf '%s %s\n' "$NAME" "$TAG"; cat "$DIR/SHA256SUMS"; } > "$WORK/message"
for key in $KEYS; do
  # An Ed25519 SubjectPublicKeyInfo is a 12-byte DER prefix (30 2a 30 05 06 03
  # 2b 65 70 03 21 00, base64 MCowBQYDK2VwAyEA) and the raw 32-byte key.
  { printf 'MCowBQYDK2VwAyEA' | base64 -d; printf '%s' "$key" | base64 -d; } > "$WORK/pub.der"
  if "$OPENSSL" pkeyutl -verify -rawin -pubin -keyform DER -inkey "$WORK/pub.der" \
       -sigfile "$DIR/SHA256SUMS.ed25519" -in "$WORK/message" > /dev/null 2>&1; then
    (cd "$DIR" && sha256sum -c --quiet --strict SHA256SUMS) || { echo "::error::a file does not match SHA256SUMS"; exit 1; }
    echo "SHA256SUMS.ed25519 verifies for $TAG with an embedded key"
    exit 0
  fi
done
echo "::error::SHA256SUMS.ed25519 is not a signature by an embedded key over $TAG"
exit 1
