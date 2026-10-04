#!/bin/sh
# Installs, checks and removes a .deb or .rpm in a clean container, as root.
#
#   sh packaging/linux/install_check.sh <package> <commit>
#
# The package manager resolves the declared libraries; the binary reports the
# commit, opens its window offscreen and on a real X server (Xvfb, the xcb
# platform that a desktop uses), the menu entry validates; removal takes the
# binary and the menu entry away.
set -eu
pkg="$1"; commit="$2"; name=routemap
short=$(printf %.12s "$commit")
ok() { echo "ok: $*"; }
fail() { echo "::error::$*"; exit 1; }

case "$pkg" in
  *.deb)
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends "./$pkg" xvfb xauth desktop-file-utils >/dev/null
    remove() { apt-get remove -y -qq "$name" >/dev/null; } ;;
  *.rpm)
    dnf install -y -q "./$pkg" xorg-x11-server-Xvfb desktop-file-utils >/dev/null
    remove() { dnf remove -y -q "$name" >/dev/null; } ;;
  *) fail "not a .deb or .rpm: $pkg" ;;
esac
ok "installed $pkg with its dependencies"

v=$("$name" --version)
echo "$v" | grep -q "commit $short" || fail "--version says '$v', not commit $short"
ok "/usr/bin/$name reports commit $short"
desktop-file-validate "/usr/share/applications/$name.desktop" || fail "menu entry does not validate"
ok "menu entry /usr/share/applications/$name.desktop validates"
test -s "/usr/share/pixmaps/$name.png" || fail "icon missing"
ok "icon in /usr/share/pixmaps"

QT_QPA_PLATFORM=offscreen "$name" --smoke-test /tmp/smoke-offscreen >/dev/null
grep -q "commit $short" /tmp/smoke-offscreen/result.txt || fail "offscreen smoke test"
ok "window opens offscreen"
Xvfb :99 -screen 0 1280x800x24 >/tmp/xvfb.log 2>&1 &
xvfb=$!
sleep 2
DISPLAY=:99 QT_QPA_PLATFORM=xcb "$name" --smoke-test /tmp/smoke-xcb >/dev/null
grep -q "commit $short" /tmp/smoke-xcb/result.txt || fail "xcb smoke test"
ok "window opens on an X server (xcb), so the declared libraries are enough"
kill "$xvfb" 2>/dev/null || true

remove
test ! -e "/usr/bin/$name" || fail "binary left after removal"
test ! -e "/usr/share/applications/$name.desktop" || fail "menu entry left after removal"
ok "removed cleanly"
echo "all package checks passed"
