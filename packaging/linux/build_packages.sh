#!/bin/sh
# Builds the .deb and .rpm around the one-file binary. Used by build.yml and
# installers.yml, so the packages are built the same way everywhere.
#
#   sh packaging/linux/build_packages.sh <binary> <version> <run number> <out dir>
#
# nfpm 2.47.0 is downloaded and checked against its pinned SHA-256.
set -eu
binary="$1"; version="$2"; run="$3"; out="$4"
NFPM_URL=https://github.com/goreleaser/nfpm/releases/download/v2.47.0/nfpm_2.47.0_Linux_x86_64.tar.gz
NFPM_SHA256=0660ca602b2d2d2ae4781a06c692b3eeb9d437ffea05b831d76e41f4a3188783
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
curl -fsSL -o "$tmp/nfpm.tar.gz" "$NFPM_URL"
echo "$NFPM_SHA256  $tmp/nfpm.tar.gz" | sha256sum -c -
tar -xzf "$tmp/nfpm.tar.gz" -C "$tmp" nfpm
python3 "$here/make_packages.py" "$(cd "$(dirname "$binary")" && pwd)/$(basename "$binary")" "$version" "$run" > "$tmp/nfpm.yaml"
mkdir -p "$out"
"$tmp/nfpm" package -f "$tmp/nfpm.yaml" -p deb -t "$out/"
"$tmp/nfpm" package -f "$tmp/nfpm.yaml" -p rpm -t "$out/"
dpkg-deb --info "$out"/*.deb
dpkg-deb --contents "$out"/*.deb
