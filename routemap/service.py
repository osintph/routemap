"""
The app's use of the engine, in one place, for the window and the CLI alike.

Settings in, engine calls out: which sources are on, where the cache lives,
which tool and flags run, where the trace starts. Qt-free, so the CLI and the
window cannot drift apart in how they trace or what they send.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
import pathlib
import re
import sys
import threading
from typing import Callable

from routemap import config, policy
from routemap.__about__ import NAME, REPO_SLUG, REPO_URL, USER_AGENT_PRODUCT, VERSION
from routemap_engine import (Route, SqliteCache, TraceOptions, analyse, cities, default_sources,
                             run_trace, sitecodes, whereami)
from routemap_engine.geo import Sources
from routemap_engine.geo import loss_verdict as geo_loss_verdict

ORIGIN_HOW_IP = "ip"
EXPORT_FORMAT = "routemap/route-export"
# 2 (0.2.0): optional "insight" (AS path, countries, RIPE data) and "comparison".
# Readers of version 1 files keep working: both are additions.
EXPORT_FORMAT_VERSION = 2


def startup() -> None:
    """Things to settle once per process: a refreshed site-code table, if any."""
    config.tighten()
    sitecodes.use_data_file(config.site_codes_path())


def user_agent() -> str:
    return f"{USER_AGENT_PRODUCT} (+{REPO_URL}; traceroute geolocation)"


# How RIPEstat identifies this app's traffic (its "sourceapp" parameter).
SOURCEAPP = f"{NAME}-desktop"


_CITY_READERS: dict = {}


def offline_city():
    """The DB-IP Lite City reader for the installed file, or None. One reader per
    file per process; a newer month installed later gets its own."""
    from routemap import dbip
    db = dbip.city_database()
    if db is None:
        return None
    reader = _CITY_READERS.get(db.path)
    if reader is None:
        from routemap_engine.offline import OfflineCity
        try:
            reader = OfflineCity(db.path)
        except Exception:  # noqa: BLE001 - a broken file is the same as no file
            return None
        _CITY_READERS.clear()
        _CITY_READERS[db.path] = reader
    return reader


def offline_sources() -> Sources:
    """Nothing contacted: site codes, local classification and, when installed,
    DB-IP Lite City."""
    from routemap_engine import OFFLINE
    city = offline_city()
    if city is None:
        return OFFLINE
    from routemap_engine.offline import layered_ip_db
    return Sources(ip_db=layered_ip_db(city, None))


def sources_for(settings: config.Settings) -> Sources:
    """The engine's sources for these settings.

    IP database placements come from DB-IP Lite City when it is installed
    (offline, sends nothing) and from RIPEstat for what the file does not know,
    or for everything when it is not installed. Settings > Online lookups off:
    Hoiho, RIPEstat and reverse DNS are all off, whatever their own boxes say.
    """
    import dataclasses

    from routemap_engine import geo
    from routemap_engine.offline import layered_ip_db

    online = bool(settings.online_lookups)
    ttl = max(1, settings.cache_ttl_days) * 86400
    hoiho_cache = SqliteCache(config.private_file(config.cache_path()), ttl_seconds=ttl)
    base = default_sources(user_agent=user_agent(), cache=hoiho_cache,
                           use_hoiho=online and settings.use_hoiho and policy.HOIHO_ALLOWED,
                           use_ip_db=False, use_ptr=online and settings.use_ptr)
    ripestat = None
    if online and settings.use_ip_db and policy.RIPESTAT_ALLOWED:
        ip_cache = SqliteCache(config.private_file(config.ip_cache_path()), ttl_seconds=ttl)

        async def ripestat(addresses: list[str]) -> dict:
            """RIPEstat, with answers kept locally for the cache lifetime. Only real
            answers are kept: a failed or empty lookup is asked again next time."""
            found, missing = {}, []
            for addr in dict.fromkeys(addresses):
                hit = ip_cache.get(addr)
                if hit:
                    found[addr] = hit
                else:
                    missing.append(addr)
            if missing:
                fetched = await geo.ip_geolocate(missing, user_agent=user_agent(), sourceapp=SOURCEAPP)
                for addr, record in fetched.items():
                    ip_cache.set(addr, record)
                    found[addr] = record
            return found

    city = offline_city()
    if city is None and ripestat is None:
        return base
    return dataclasses.replace(base, ip_db=layered_ip_db(city, ripestat))


def parse_origin_text(text: str) -> tuple[float, float, str]:
    """'14.6,121.0' or a city name -> (lat, lon, label). ValueError if neither."""
    from routemap_engine import normalise_origin

    parts = [p.strip() for p in (text or "").split(",")]
    if len(parts) == 2:
        try:
            origin = normalise_origin(float(parts[0]), float(parts[1]))
        except ValueError:
            origin = None
        if origin is not None:
            city = cities.nearest(*origin)
            return origin[0], origin[1], (city or {}).get("display") or f"{origin[0]}, {origin[1]}"
    # "Manila, PH": search the name, prefer the country if one was given.
    name, _, country = (text or "").partition(",")
    matches = cities.search(name.strip(), limit=12)
    if country.strip():
        cc = country.strip().upper()
        preferred = [m for m in matches if m["cc"] == cc]
        matches = preferred or matches
    if not matches:
        raise ValueError(f"no city or lat,lon matches {text!r}")
    best = matches[0]
    return best["lat"], best["lon"], best["display"]


async def resolve_origin(settings: config.Settings) -> tuple[float, float, str, str]:
    """(lat, lon, label, how): the chosen origin, else one public IP lookup."""
    chosen = settings.origin()
    if chosen is not None:
        return chosen[0], chosen[1], chosen[2], settings.origin_mode
    if not policy.RIPESTAT_ALLOWED:
        raise RuntimeError(policy.RIPESTAT_OFF_NOTE)
    me = await whereami.locate_me(user_agent=user_agent(), sourceapp=SOURCEAPP)
    return me["lat"], me["lon"], me["label"], ORIGIN_HOW_IP


def trace_options(settings: config.Settings, tool: str, *, cancel: threading.Event | None = None,
                  on_line: Callable[[str], None] | None = None) -> TraceOptions:
    return TraceOptions(tool=tool, flags=settings.flags_for(tool), timeout=settings.timeout_seconds,
                        cancel=cancel, on_line=on_line)


def run(target: str, settings: config.Settings, **kwargs):
    from routemap_engine.runner import pick_tool

    tool, _path = pick_tool(settings.tool)
    return run_trace(target, trace_options(settings, tool, **kwargs))


def analyse_sync(text_or_hops, origin, settings: config.Settings, progress=None) -> Route:
    return asyncio.run(analyse(text_or_hops, origin, sources=sources_for(settings),
                               progress=progress))


# -------------------------------------------------------------------- export ---

def export_json(route: Route | dict, *, target: str | None, trace_text: str,
                argv: list[str] | None, source: str, origin_how: str | None,
                insight: dict | None = None, comparison: dict | None = None) -> str:
    """The JSON export: the route model plus how the trace was made."""
    body = route.to_dict() if isinstance(route, Route) else dict(route)
    document = {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_FORMAT_VERSION,
        "generator": f"{NAME} {VERSION}",
        "exported_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "target": target,
        "origin_how": origin_how,
        "trace": {"source": source, "tool": os.path.basename(argv[0]) if argv else None,
                  "argv": [os.path.basename(argv[0])] + list(argv[1:]) if argv else None,
                  "text": trace_text},
        "route": body,
        # Only loss that reaches the destination; rate-limited hops by number.
        "loss": geo_loss_verdict(body.get("hops") or []),
        "schema": "https://github.com/osintph/routemap-engine/blob/main/routemap_engine/route.schema.json",
    }
    if insight:
        from routemap import insight as _insight
        document["insight"] = insight
        document["attributions"] = _insight.attributions(insight)
    if comparison:
        document["comparison"] = comparison
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def export_stem(target: str | None, when: _dt.datetime) -> str:
    """The suggested export file name without extension: letters, digits, dot,
    underscore and hyphen only, so a target from a file (a pasted or opened
    trace) cannot make the save dialog start in another folder (RM-13)."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", target or "")[:80].strip(".-") or "trace"
    return f"route-{safe}-{when.strftime('%Y%m%d-%H%M')}"


def tool_label(argv: list[str] | None) -> str:
    """'traceroute -m 30 -q 3 -w 1' from an argv, without the path or the target."""
    if not argv:
        return ""
    return " ".join([os.path.basename(argv[0])] + list(argv[1:-1]))


# -------------------------------------------------------------- update check ---

RELEASE_TAG = re.compile(r"v\d+\.\d+\.\d+(?:-[a-z]+\.\d+)?")
ASSET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,199}")
SHA256 = re.compile(r"sha256:([0-9a-f]{64})")


def atlas_credit_view(balance, cost: int) -> dict:
    """What the Atlas trace dialog says about credits, from an atlas.Balance.

    Returns {"state", "lines", "can_run", "fix_key"}. ``lines`` are
    (label, value) rows for "ok" and "low", or a single ("", sentence) row
    otherwise. Only an unknown or invalid key (401) and a balance that cannot
    pay stop the trace; a key that may not read the balance (403) and a
    balance that could not be read do not, because RIPE's own check at
    scheduling time is the one that counts.
    """
    state = getattr(balance, "state", None) or "unavailable"
    reason = (getattr(balance, "message", "") or "").strip().rstrip(".")
    said = f' RIPE said: "{reason}".' if reason else ""
    if state == "ok":
        current = balance.current
        after = current - cost
        if after < 0:
            return {"state": "low", "can_run": False, "fix_key": False, "lines": [
                ("", f"Not enough credits. Your balance is {current:,} credits and this trace "
                     f"costs {cost}; RIPE would refuse it.")]}
        lines = [("Your balance", f"{current:,} credits"),
                 ("This trace", f"{cost} credits (one-off traceroute, one probe)"),
                 ("After it", f"{after:,} credits")]
        income, spent = balance.daily_income, balance.daily_expenditure
        if income is not None or spent is not None:
            parts = []
            if income is not None:
                parts.append(f"+{income:,} a day earned")
            if spent is not None:
                parts.append(f"{spent:,} a day spent")
            lines.append(("RIPE's estimate", ", ".join(parts)))
        return {"state": "ok", "can_run": True, "fix_key": False, "lines": lines}
    if state == "bad_key":
        return {"state": "bad_key", "can_run": False, "fix_key": True, "lines": [
            ("", "RIPE Atlas did not accept your API key, so the trace cannot run either."
                 f"{said} Check or replace the key in Settings \u203a RIPE Atlas.")]}
    if state == "no_permission":
        return {"state": "no_permission", "can_run": True, "fix_key": False, "lines": [
            ("", "Your key may not read the balance, so it is not shown. The trace can still "
                 f"run.{said} To see the balance here, give the key the \u201ccredits read\u201d "
                 "permission at atlas.ripe.net/keys.")]}
    return {"state": "unavailable", "can_run": True, "fix_key": False, "lines": [
        ("", f"The balance could not be read: RIPE Atlas did not answer. This trace costs "
             f"{cost} credits; RIPE refuses it if the account cannot pay.")]}


def release_url(url) -> str | None:
    """*url* when it is a page or file of this repository on github.com over
    https, else None (hardening 9): the update check opens nothing else."""
    from urllib.parse import urlsplit
    if not isinstance(url, str) or any(c in url for c in "\\@ \t\r\n"):
        return None
    parts = urlsplit(url)
    path = parts.path
    if (parts.scheme != "https" or parts.netloc != "github.com" or not path.startswith(f"/{REPO_SLUG}/")
            or ".." in path.split("/") or "%2e" in path.lower() or "%5c" in path.lower()):
        return None
    return url


async def latest_release() -> dict | None:
    """The newest release on GitHub, pre-releases included, as {tag, page, assets:
    {name: download URL}, digests: {name: SHA-256}}; None when there is none.
    One request, read under the engine's response cap. Only a release tag, and
    only this repository's own URLs, are kept."""
    from routemap_engine import httpclient

    async with httpclient.client() as client:
        response = await client.get(f"https://api.github.com/repos/{REPO_SLUG}/releases",
                                    params={"per_page": 1}, timeout=10.0,
                                    headers={"User-Agent": user_agent(),
                                             "Accept": "application/vnd.github+json"})
        response.raise_for_status()
        releases = response.json() or []
    if not isinstance(releases, list) or not releases or not isinstance(releases[0], dict):
        return None
    rel = releases[0]
    tag = rel.get("tag_name")
    if not isinstance(tag, str) or not RELEASE_TAG.fullmatch(tag):
        return None
    assets, digests = {}, {}
    for a in rel.get("assets") or []:
        name = a.get("name") if isinstance(a, dict) else None
        url = release_url(a.get("browser_download_url")) if isinstance(a, dict) else None
        if not (isinstance(name, str) and ASSET_NAME.fullmatch(name) and url
                and url.startswith(f"{REPO_URL}/releases/download/")):
            continue
        assets[name] = url
        digest = SHA256.fullmatch(str(a.get("digest") or ""))
        if digest:
            digests[name] = digest.group(1)
    return {"tag": tag, "page": release_url(rel.get("html_url")) or f"{REPO_URL}/releases",
            "assets": assets, "digests": digests}


def verify_command(name: str, system: str | None = None) -> str:
    """The command that prints *name*'s SHA-256 on this platform."""
    system = system or sys.platform
    if system.startswith("win"):
        return f"Get-FileHash -Algorithm SHA256 {name}"
    if system == "darwin":
        return f"shasum -a 256 {name}"
    return f"sha256sum {name}"


def release_order(tag: str) -> tuple:
    """Sortable form of a tag or version in either spelling: 'v0.2.0-beta.2' and
    '0.2.0b2' are equal, a beta sorts before its final release."""
    import re

    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:-?(alpha|beta|rc|a|b)\.?(\d+))?$", tag.strip())
    if not m:
        return ()
    kind = {"alpha": "a", "beta": "b", "a": "a", "b": "b", "rc": "rc"}.get(m.group(4) or "", "z")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), kind, int(m.group(5) or 0))


def linux_family(os_release: str | None = None) -> str:
    """'deb', 'rpm' or '' from /etc/os-release (ID and ID_LIKE)."""
    if os_release is None:
        try:
            os_release = pathlib.Path("/etc/os-release").read_text(encoding="utf-8")
        except OSError:
            return ""
    ids = set()
    for line in os_release.splitlines():
        key, _, value = line.partition("=")
        if key in ("ID", "ID_LIKE"):
            ids.update(value.strip().strip('"').lower().split())
    if ids & {"debian", "ubuntu"}:
        return "deb"
    if ids & {"fedora", "rhel", "centos", "suse", "opensuse"}:
        return "rpm"
    return ""


def installer_for(assets: dict[str, str], system: str | None = None, machine: str | None = None,
                  family: str | None = None, appimage: bool | None = None) -> tuple[str, str] | None:
    """The release file to offer on this machine, as (name, URL): the Windows
    installer, the DMG for this Mac's architecture, on Linux the AppImage when
    running as one, else the .deb or .rpm for the distribution, else the AppImage.
    None when the release has nothing for this platform."""
    import platform as _platform

    system = system or sys.platform
    machine = (machine or _platform.machine()).lower()
    names = list(assets)

    def first(*suffixes: str) -> tuple[str, str] | None:
        for suffix in suffixes:
            for name in names:
                if name.endswith(suffix):
                    return name, assets[name]
        return None

    if system.startswith("win"):
        return first("-windows-x86_64-setup.exe", "-windows-x86_64.zip")
    if system == "darwin":
        arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
        return first(f"-macos-{arch}.dmg")
    if system.startswith("linux"):
        if appimage if appimage is not None else bool(os.environ.get("APPIMAGE")):
            return first("-linux-x86_64.AppImage")
        family = linux_family() if family is None else family
        # Release file names since 0.2.0-beta.2, then the nfpm-style names before.
        wanted = {"deb": ("-linux-x86_64.deb", "_amd64.deb"),
                  "rpm": ("-linux-x86_64.rpm", ".x86_64.rpm")}.get(family, ())
        return first(*wanted, "-linux-x86_64.AppImage", "-linux-x86_64.tar.gz")
    return None
