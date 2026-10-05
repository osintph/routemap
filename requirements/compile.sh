#!/bin/bash
# Compiles every hash lock except requirements/app.txt (the app's own runtime
# lock, compiled with it): build backends, build tools, tests, the SBOM tool
# and the site. One lock per job's needs, each for Windows, macOS and Linux and
# Python 3.11 to 3.13, with a SHA-256 for every file. The locks that are
# installed on top of app.txt are constrained by it, so no package is pinned
# to two versions.
#
#   requirements/compile.sh            (uv 0.9.2 on PATH, or UV=/path/to/uv)
#
# Dependabot (.github/dependabot.yml) proposes updates to these files.
set -euo pipefail
cd "$(dirname "$0")/.."
UV="${UV:-uv}"
"$UV" --version | grep -q '^uv 0\.9\.2' || { echo "compile.sh: needs uv 0.9.2 (got: $("$UV" --version))" >&2; exit 1; }
common=(--universal --python-version 3.11 --generate-hashes --quiet)
constraint=()
[ -f requirements/app.txt ] && constraint=(-c requirements/app.txt)
"$UV" pip compile "${common[@]}" requirements/build-backends.in -o requirements/build-backends.txt
"$UV" pip compile "${common[@]}" ${constraint[@]+"${constraint[@]}"} requirements/build-tools.in -o requirements/build-tools.txt
"$UV" pip compile "${common[@]}" ${constraint[@]+"${constraint[@]}"} requirements/tests.in -o requirements/tests.txt
"$UV" pip compile "${common[@]}" ${constraint[@]+"${constraint[@]}"} requirements/audit.in -o requirements/audit.txt
"$UV" pip compile "${common[@]}" site/requirements.in -o site/requirements.txt
