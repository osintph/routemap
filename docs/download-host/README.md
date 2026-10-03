# The optional pre-release download site

Released versions of Route Map are published on
[GitHub Releases](https://github.com/osintph/routemap/releases), with
`SHA256SUMS` and its GPG signature. That is the only channel users need.

This folder describes a second, optional channel: a small static site with a
login for each tester, for builds handed out before they are released. The
build workflow can upload every tagged build there as well; when its secrets
are not set, that step is skipped.

## How it works

- nginx serves `/srv/routemap-downloads/` behind HTTP basic auth, one login
  per tester (`routemap-downloads.conf`). One folder per version; the workflow
  writes each folder's `index.html` and the root index, which lists every
  version and the GPG release key's fingerprint.
- The workflow uploads with `rsync` over SSH as a deploy user whose key is
  restricted to rsync in that one folder:
  `command="/usr/bin/rrsync /srv/routemap-downloads",restrict ssh-ed25519 AAAA...`
- `scripts/testers.sh` adds, disables, re-enables and lists tester logins on
  the host, and prints the welcome email for one tester in one command.

## Hardening

- **Not indexed.** Every response, including 401, 403 and 404, carries
  `X-Robots-Tag: noindex, nofollow`; `/robots.txt` is the one file served
  without a login, and disallows everything.
- **Not cached.** Every response carries `Cache-Control: private, no-store`.
  Behind a CDN this matters: a CDN that caches a protected file once can serve
  it to anyone afterwards. With Cloudflare, check that `cf-cache-status` is
  `DYNAMIC` or `BYPASS` (never `HIT`) on every kind of path, and add a Cache
  Rule for the hostname (bypass cache, browser TTL "respect origin"): the
  zone's Browser Cache TTL otherwise rewrites the header for file types it
  considers static.
- **Failed logins.** fail2ban (`fail2ban-jail.conf`, `fail2ban-action.conf`)
  bans an address for an hour after 5 failed logins in 10 minutes. The ban is
  a `deny` line in nginx, not a firewall rule, because behind a CDN the
  firewall only sees the CDN. nginx must recover the visitor's address first
  (the `real_ip` lines in the vhost). Unban:
  `sudo fail2ban-client set routemap-downloads unbanip ADDRESS`.
- Logs rotate weekly (`logrotate.conf`).

## Settings the workflow needs

Environment `downloads` in the repository, secrets:

| Secret | Value |
|---|---|
| `DOWNLOAD_HOST` | the host |
| `DOWNLOAD_PORT` | its SSH port |
| `DOWNLOAD_USER` | the restricted deploy user |
| `DOWNLOAD_SSH_KEY` | the private half of the deploy key |
| `DOWNLOAD_KNOWN_HOSTS` | `ssh-keyscan -p PORT HOST`, checked against the host's own keys |
| `GPG_RELEASE_KEY` | `gpg --armor --export-secret-keys FPR` of the release key |
| `GPG_RELEASE_PASSPHRASE` | its passphrase |

The GPG secrets also sign the GitHub Release. Without the download secrets the
upload to this site is skipped. Nothing is ever published unsigned.

## Testers

`scripts/testers.sh` reads `~/.routemap-testers/testers.env` (outside any
repository; the variables are listed at the top of the script). nginx re-reads
the htpasswd file on every request, so changes apply at once. Passwords are
generated from the OS's cryptographic random source, hashed on the host
(SHA-512 crypt), and shown once, in the welcome email text.
