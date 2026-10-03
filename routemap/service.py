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
import threading
from typing import Callable

from routemap import config, policy
from routemap.__about__ import NAME, REPO_SLUG, REPO_URL, USER_AGENT_PRODUCT, __version__
from routemap_engine import (Route, SqliteCache, TraceOptions, analyse, cities, default_sources,
                             run_trace, sitecodes, whereami)
from routemap_engine.geo import Sources

ORIGIN_HOW_IP = "ip"
EXPORT_FORMAT = "routemap/route-export"
EXPORT_FORMAT_VERSION = 1


def startup() -> None:
    """Things to settle once per process: a refreshed site-code table, if any."""
    sitecodes.use_data_file(config.site_codes_path())


def user_agent() -> str:
    return f"{USER_AGENT_PRODUCT} (+{REPO_URL}; traceroute geolocation)"


# How RIPEstat identifies this app's traffic (its "sourceapp" parameter).
SOURCEAPP = f"{NAME}-desktop"


def sources_for(settings: config.Settings) -> Sources:
    import dataclasses

    from routemap_engine import geo

    ttl = max(1, settings.cache_ttl_days) * 86400
    hoiho_cache = SqliteCache(config.cache_path(), ttl_seconds=ttl)
    base = default_sources(user_agent=user_agent(), cache=hoiho_cache,
                           use_hoiho=settings.use_hoiho and policy.HOIHO_ALLOWED,
                           use_ip_db=False, use_ptr=settings.use_ptr)
    if not (settings.use_ip_db and policy.RIPESTAT_ALLOWED):
        return base
    ip_cache = SqliteCache(config.ip_cache_path(), ttl_seconds=ttl)

    async def ip_db(addresses: list[str]) -> dict:
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

    return dataclasses.replace(base, ip_db=ip_db)


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
                argv: list[str] | None, source: str, origin_how: str | None) -> str:
    """The JSON export: the route model plus how the trace was made."""
    body = route.to_dict() if isinstance(route, Route) else dict(route)
    document = {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_FORMAT_VERSION,
        "generator": f"{NAME} {__version__}",
        "exported_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "target": target,
        "origin_how": origin_how,
        "trace": {"source": source, "tool": os.path.basename(argv[0]) if argv else None,
                  "argv": [os.path.basename(argv[0])] + list(argv[1:]) if argv else None,
                  "text": trace_text},
        "route": body,
        "schema": "https://github.com/" + REPO_SLUG + "/blob/main/routemap_engine/route.schema.json",
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def tool_label(argv: list[str] | None) -> str:
    """'traceroute -m 30 -q 3 -w 1' from an argv, without the path or the target."""
    if not argv:
        return ""
    return " ".join([os.path.basename(argv[0])] + list(argv[1:-1]))


# -------------------------------------------------------------- update check ---

async def latest_release() -> str | None:
    """The newest release tag on GitHub, pre-releases included. One request."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.github.com/repos/{REPO_SLUG}/releases",
                                    params={"per_page": 1}, timeout=10.0,
                                    headers={"User-Agent": user_agent(),
                                             "Accept": "application/vnd.github+json"})
    response.raise_for_status()
    releases = response.json() or []
    return releases[0].get("tag_name") if releases else None
