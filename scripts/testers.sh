#!/bin/bash
# Logins for the optional pre-release download site, and their welcome email.
# Public releases are on GitHub Releases and need no login; this channel is for
# builds handed to a few testers before they are released.
#
#   scripts/testers.sh add --login jdoe --name "Jane Doe" --email jane@example.com
#   scripts/testers.sh disable jdoe
#   scripts/testers.sh enable jdoe          (issues a fresh password)
#   scripts/testers.sh list
#
# "add" does everything for one tester in one command: creates the login on the
# download host (htpasswd entry, SHA-512 crypt), records it in the local testers
# ledger, and prints the welcome email (download URL, login, password). The
# password is shown once, in that email text; it is not stored anywhere in the
# clear.
#
# Config: ~/.routemap-testers/testers.env (outside any repository):
#   DOWNLOAD_HOST=downloads.example.org      host for SSH
#   DOWNLOAD_PORT=22
#   DOWNLOAD_ADMIN=ubuntu                    SSH user allowed to edit the htpasswd file
#   HTPASSWD_FILE=/etc/nginx/routemap-testers.htpasswd
#   HTPASSWD_SUDO=1                          1 if editing it needs sudo
#   DOWNLOAD_URL=https://downloads.example.org/
#   GPG_FINGERPRINT="XXXX XXXX ..."          the release key, for the email
#   FEEDBACK_EMAIL=beta@example.org
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
CONF="${ROUTEMAP_TESTERS_ENV:-$HOME/.routemap-testers/testers.env}"
LEDGER="${ROUTEMAP_TESTERS_LEDGER:-$HOME/.routemap-testers/testers.csv}"
PY="${PYTHON:-$REPO/.venv/bin/python}"

die() { printf 'testers.sh: %s\n' "$*" >&2; exit 1; }
[[ -f "$CONF" ]] || die "no config at $CONF (see the top of this script)"
# shellcheck disable=SC1090
source "$CONF"
: "${DOWNLOAD_HOST:?}" "${HTPASSWD_FILE:?}" "${DOWNLOAD_URL:?}"
DOWNLOAD_PORT="${DOWNLOAD_PORT:-22}"
DOWNLOAD_ADMIN="${DOWNLOAD_ADMIN:-$USER}"
SUDO=""; [[ "${HTPASSWD_SUDO:-0}" == "1" ]] && SUDO="sudo"

remote() {
    # TESTERS_REMOTE_LOCAL=1 runs the "remote" side here, for the test suite only.
    if [[ "${TESTERS_REMOTE_LOCAL:-0}" == "1" ]]; then bash -c "$*"; return; fi
    ssh -p "$DOWNLOAD_PORT" -o BatchMode=yes "$DOWNLOAD_ADMIN@$DOWNLOAD_HOST" "$@"
}

valid_login() { [[ "$1" =~ ^[a-z0-9][a-z0-9._-]{1,31}$ ]] || die "login must be 2-32 of a-z 0-9 . _ - : $1"; }

new_password() {
    # 20 characters from a 56-symbol alphabet without look-alikes (no 0 O 1 l I),
    # from the OS's cryptographic random source. (Not tr < /dev/urandom | head:
    # under pipefail that pipeline dies of SIGPIPE.)
    "$PY" -c 'import secrets; a = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"; print("".join(secrets.choice(a) for _ in range(20)))'
}

hash_password() {
    # Hashed on the download host, so the crypt format is one its nginx accepts.
    printf '%s' "$1" | remote "openssl passwd -6 -stdin"
}

set_entry() {
    local login="$1" hash="$2"
    # Remove any existing or disabled line for the login, then append the new one.
    remote "$SUDO touch '$HTPASSWD_FILE' && $SUDO sed -i -e '/^$login:/d' -e '/^#disabled:$login:/d' '$HTPASSWD_FILE' \
            && printf '%s\n' '$login:$hash' | $SUDO tee -a '$HTPASSWD_FILE' > /dev/null"
}

ledger_row() {
    mkdir -p "$(dirname "$LEDGER")"
    [[ -f "$LEDGER" ]] || { echo "when_utc,action,login,name,email" > "$LEDGER"; chmod 600 "$LEDGER"; }
    printf '%s,%s,%s,"%s",%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "${3//\"/}" "${4:-}" >> "$LEDGER"
}

cmd_add() {
    local login="" name="" email=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --login) login="$2"; shift 2 ;;
            --name) name="$2"; shift 2 ;;
            --email) email="$2"; shift 2 ;;
            *) die "unknown option $1" ;;
        esac
    done
    [[ -n "$login" && -n "$name" && -n "$email" ]] || die "add needs --login, --name and --email"
    valid_login "$login"
    if remote "grep -q '^$login:' '$HTPASSWD_FILE' 2>/dev/null"; then
        die "login $login already exists (disable it first, or choose another)"
    fi

    local password hash
    password="$(new_password)"
    hash="$(hash_password "$password")"
    [[ "$hash" == '$6$'* ]] || die "the host did not return a SHA-512 crypt hash"
    set_entry "$login" "$hash"
    ledger_row add "$login" "$name" "$email"

    cat <<MAIL
Subject: Your Route Map beta access

Hi ${name%% *},

Thank you for testing Route Map before its next release. The pre-release
builds are on a small download site; please keep this login to yourself.

Download page:  ${DOWNLOAD_URL}
Login:          ${login}
Password:       ${password}

Route Map is free and open source (AGPL-3.0): https://github.com/osintph/routemap
Released versions are on GitHub Releases and need no login.

Installing
- Windows 10/11: download routemap-<version>-windows-x86_64.zip, extract it,
  and run routemap.exe in the "Route Map" folder (routemap-cli.exe beside it
  is the command line). The build is not code-signed yet, so SmartScreen may
  say "Windows protected your PC": choose More info, then Run anyway.
- macOS 12 or later: open the .dmg for your Mac (macos-arm64 for Apple silicon,
  macos-x86_64 for Intel) and drag Route Map to Applications. The first time,
  right-click it, choose Open, then Open again.
- Linux x86_64: chmod +x the .AppImage and run it. Tracing needs traceroute
  installed (for example: sudo apt install traceroute).

Checking your download (optional): each version folder has SHA256SUMS and its
GPG signature, SHA256SUMS.asc, made with the release key
${GPG_FINGERPRINT:-(fingerprint on the download page)}.

Feedback: please open an issue at https://github.com/osintph/routemap/issues
If you would rather not use GitHub, reply to this email${FEEDBACK_EMAIL:+ or write to ${FEEDBACK_EMAIL}}.
Your OS and version, the Route Map version (Help > About), what you traced and
what you expected help most. A screenshot helps too.

Thank you,
osintph
MAIL
}

cmd_disable() {
    local login="${1:-}"; valid_login "$login"
    remote "grep -q '^$login:' '$HTPASSWD_FILE'" || die "no active login $login"
    remote "$SUDO sed -i 's/^$login:/#disabled:$login:/' '$HTPASSWD_FILE'"
    ledger_row disable "$login" "" ""
    echo "disabled $login (the download site refuses it from now on)"
}

cmd_enable() {
    local login="${1:-}"; valid_login "$login"
    remote "grep -q '^#disabled:$login:' '$HTPASSWD_FILE'" || die "no disabled login $login"
    local password hash
    password="$(new_password)"
    hash="$(hash_password "$password")"
    set_entry "$login" "$hash"
    ledger_row enable "$login" "" ""
    echo "re-enabled $login with a new password: $password"
}

cmd_list() {
    remote "cat '$HTPASSWD_FILE' 2>/dev/null" | awk -F: '
        /^#disabled:/ { printf "%-24s disabled\n", $2; next }
        /^[^#]/ && NF > 1 { printf "%-24s active\n", $1 }'
}

case "${1:-}" in
    add) shift; cmd_add "$@" ;;
    disable) shift; cmd_disable "$@" ;;
    enable) shift; cmd_enable "$@" ;;
    list) cmd_list ;;
    *) sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
