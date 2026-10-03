#!/bin/bash
# Checks against a PACKAGED CLI binary, run by CI before the smoke tests.
#
#   bash packaging/cli_check.sh <routemap binary>
#
# 1. It parses a recorded trace offline and writes valid JSON.
# 2. Redirected output is UTF-8 on every platform (beta.2's Windows build
#    wrote the ANSI code page): a missing file named Zürich.txt makes the
#    CLI print that name to stderr, which must come out as UTF-8.
set -euo pipefail
BIN="$1"
TMP="${RUNNER_TEMP:-/tmp}"

"$BIN" parse tests/fixtures/routemap/heise_traceroute.txt --offline > "$TMP/parse.json"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["hops"], d; print("ok: parse wrote", len(d["hops"]), "hops")' "$TMP/parse.json" \
  || python -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["hops"], d; print("ok: parse wrote", len(d["hops"]), "hops")' "$TMP/parse.json"

set +e
"$BIN" parse "$TMP/Z$(printf '\xc3\xbc')rich.txt" > /dev/null 2> "$TMP/utf8.err"
set -e
cat "$TMP/utf8.err"
check='import sys; t=open(sys.argv[1],"rb").read().decode("utf-8"); assert "Zürich" in t, t; print("ok: redirected output is UTF-8")'
python3 -c "$check" "$TMP/utf8.err" || python -c "$check" "$TMP/utf8.err"
