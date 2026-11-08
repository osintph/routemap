#!/bin/bash
# Checks against a PACKAGED CLI binary, run by CI before the smoke tests.
#
#   bash packaging/cli_check.sh <routemap binary>
#
# 1. It parses a recorded trace offline and writes valid JSON.
# 2. Redirected output is UTF-8 on every platform (beta.2's Windows build
#    wrote the ANSI code page): a missing file named Zürich.txt makes the
#    CLI print that name to stderr, which must come out as UTF-8.
# 3. --list-interfaces reads the real adapter list and shows at least one with
#    a kind. It sends nothing.
# 4. Watch's header line, redirected, ends where it should. ICMP to loopback
#    only: nothing leaves the machine. Where unprivileged ICMP is off (Linux
#    runners) Watch refuses with exit code 3 before the header, and this is skipped.
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

"$BIN" --list-interfaces > "$TMP/interfaces.txt"
check='import re,sys; t=open(sys.argv[1],"rb").read().decode("utf-8"); assert re.search(r"^[- ] .+, (physical|tunnel|unclassified), (up|down)", t, re.M), t; print("ok: --list-interfaces lists an adapter with a kind")'
python3 -c "$check" "$TMP/interfaces.txt" || python -c "$check" "$TMP/interfaces.txt"

set +e
"$BIN" --watch 127.0.0.1 --count 1 --offline --origin "14.6,121" --json > "$TMP/watch.json" 2> "$TMP/watch.err"
rc=$?
set -e
if [ "$rc" = 3 ]; then
  cat "$TMP/watch.err"; echo "skip: Watch needs unprivileged ICMP, off on this runner"
else
  check='import sys; t=open(sys.argv[1],"rb").read().decode("utf-8"); h=[l for l in t.splitlines() if " watch to " in l]; assert h and h[0].endswith("(Ctrl+C stops)"), repr(h); print("ok: Watch header ends cleanly")'
  [ "$rc" = 0 ] || { cat "$TMP/watch.err"; echo "Watch exited $rc"; exit 1; }
  python3 -c "$check" "$TMP/watch.err" || python -c "$check" "$TMP/watch.err"
fi
