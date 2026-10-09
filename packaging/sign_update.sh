#!/bin/bash
# Signs a release's SHA256SUMS for the in-app update, with the Ed25519 key.
#
#   UPDATE_ED25519_KEY=<PEM> packaging/sign_update.sh <tag> <release-dir>
#
# Writes <release-dir>/SHA256SUMS.ed25519: 64 raw bytes, an Ed25519 signature
# over "<NAME> <tag>\n" followed by SHA256SUMS exactly as it is (the message
# routemap/updater.py checks). The key is written only to a folder under
# $RUNNER_TEMP that only this user can read, and removed on exit whatever
# happens; the workflow removes the folder again in an always() step.
# OPENSSL may name an OpenSSL 3 binary (pkeyutl -rawin needs 3.0 or later).
set -euo pipefail
TAG="$1"
DIR="$2"
OPENSSL="${OPENSSL:-openssl}"
cd "$(dirname "$0")/.."
[ -n "${UPDATE_ED25519_KEY:-}" ] || { echo "::error::UPDATE_ED25519_KEY is not set: nothing is published without the update signature."; exit 1; }
[ -f "$DIR/SHA256SUMS" ] || { echo "::error::$DIR/SHA256SUMS is missing"; exit 1; }
# The name as routemap/__about__.py states it, read without importing Python.
NAME="$(sed -n 's/^NAME = "\([a-z0-9-]*\)"$/\1/p' routemap/__about__.py)"
[ -n "$NAME" ] || { echo "::error::NAME not found in routemap/__about__.py"; exit 1; }
WORK="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/routemap-update-sign.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
chmod 700 "$WORK"
(umask 077; printf '%s\n' "$UPDATE_ED25519_KEY" > "$WORK/key.pem")
{ printf '%s %s\n' "$NAME" "$TAG"; cat "$DIR/SHA256SUMS"; } > "$WORK/message"
"$OPENSSL" pkeyutl -sign -rawin -inkey "$WORK/key.pem" -in "$WORK/message" -out "$DIR/SHA256SUMS.ed25519"
[ "$(wc -c < "$DIR/SHA256SUMS.ed25519" | tr -d ' ')" = 64 ] || { echo "::error::the update signature is not 64 bytes"; exit 1; }
