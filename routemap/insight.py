"""
What the app says about a route beyond where its hops are: the AS path, the
countries it crossed, RPKI and visibility for the destination prefix, what
RIPE's route collectors see, recent BGP activity, a typical latency for the
same trip, and an anycast note.

Two stages, so the map never waits for the network:

  offline(route)        ASNs from the bundled DB-IP Lite ASN file, the AS
                        path, countries, anycast. Instant, sends nothing.
  online(route, ...)    RIPEstat and the RIPE Atlas baseline, only when
                        Settings > Online lookups is on. Every call is
                        rate-limited, cached and under a hard timeout; a call
                        that fails is "unavailable" and nothing else changes.

The placement logic is the engine's (routemap_engine.osint, .ripe, .baseline);
this module only decides what to ask and keeps the answers together. Qt-free,
shared by the window, the exports and the CLI.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging

from routemap import config, dbip, policy
from routemap_engine import SqliteCache, baseline, cities, osint, ripe

log = logging.getLogger(__name__)

ONLINE_BUDGET_SECONDS = 50.0      # the slow RIPEstat endpoints may take 20 s and retry once
MAX_PREFIX_LOOKUPS = 24            # network-info + RPKI per distinct public address
UNAVAILABLE = "unavailable"
OFF = "off"

_ASN = None


def _asn_reader():
    """The offline ASN reader, opened once per process."""
    global _ASN
    if _ASN is None:
        from routemap_engine.offline import OfflineAsn
        db = dbip.asn_database()
        _ASN = OfflineAsn(db.path) if db else False
    return _ASN or None


def offline(route: dict, settings: config.Settings) -> dict:
    """Add ASNs to *route*'s hops (in place) and return the offline insight."""
    reader = _asn_reader()
    if reader is not None:
        osint.enrich_offline(route, reader)
    path = osint.as_path(route)
    city = dbip.city_database()
    asn = dbip.asn_database()
    return {
        "as_path": path,
        "as_path_text": osint.as_path_text(path),
        "jurisdictions": osint.jurisdictions(route, set(settings.sensitive_countries)),
        "anycast": osint.anycast_note(route, _registered_destination(route)),
        "databases": {"asn": asn.month if asn else None, "city": city.month if city else None},
        "online": None,
    }


def _registered_destination(route: dict):
    """Where the IP database registers the destination, for the anycast check.

    Only when the destination was placed by the IP database: a hostname rule
    names the router's real site, which anycast does not move."""
    answered = [h for h in route.get("hops") or [] if h.get("min_rtt_ms") is not None]
    if not answered:
        return None
    last = answered[-1]
    if last.get("source") == "ip-db" and last.get("lat") is not None:
        return (last["lat"], last["lon"])
    return None


def _destination(route: dict) -> dict | None:
    answered = [h for h in route.get("hops") or [] if h.get("min_rtt_ms") is not None
                and any(osint.is_public(a) for a in h.get("addresses") or [])]
    return answered[-1] if answered else None


def _public(hop: dict) -> str | None:
    return next((a for a in hop.get("addresses") or [] if osint.is_public(a)), None)


def online_allowed(settings: config.Settings) -> bool:
    return bool(settings.online_lookups and policy.RIPESTAT_ALLOWED)


def client(settings: config.Settings, user_agent: str, sourceapp: str) -> ripe.RipeStat:
    cache = SqliteCache(config.private_file(config.ripe_cache_path()), ttl_seconds=30 * 86400)
    return ripe.RipeStat(user_agent=user_agent, sourceapp=sourceapp, cache=cache)


async def online(route: dict, insight: dict, settings: config.Settings, *, user_agent: str,
                 sourceapp: str, now: _dt.datetime | None = None,
                 stat: ripe.RipeStat | None = None, atlas: baseline.Baseline | None = None) -> dict:
    """Fill ``insight["online"]``. Never raises; an answer missing is UNAVAILABLE."""
    if not online_allowed(settings):
        insight["online"] = {"status": OFF}
        return insight
    stat = stat or client(settings, user_agent, sourceapp)
    atlas = atlas or baseline.Baseline(user_agent=user_agent,
                                       cache=SqliteCache(config.private_file(config.ripe_cache_path()),
                                                         ttl_seconds=86400))
    now = now or _dt.datetime.now(_dt.timezone.utc)
    result: dict = {"status": "partial", "hops": {}, "asns": {}, "prefix": None, "baseline": None,
                    "fetched_at": now.isoformat(timespec="seconds")}
    insight["online"] = result
    result["errors"] = {}
    try:
        await asyncio.wait_for(_fill(route, insight, result, stat, atlas, now), ONLINE_BUDGET_SECONDS)
        result["status"] = "done"
    except asyncio.TimeoutError:
        result["status"] = UNAVAILABLE + " (time limit)"
        log.warning("event=routemap_insight_timeout budget=%.0fs", ONLINE_BUDGET_SECONDS)
    except Exception as exc:  # noqa: BLE001 - details are never worth failing a trace
        result["status"] = UNAVAILABLE
        log.warning("event=routemap_insight_failed error=%s", exc.__class__.__name__)
    result["errors"].update(getattr(stat, "errors", {}) or {})
    return insight


async def _fill(route, insight, result, stat, atlas, now):
    hops = [h for h in route.get("hops") or [] if _public(h)][:MAX_PREFIX_LOOKUPS]

    # Per hop: the routed prefix, its origin ASN, and that pair's RPKI state.
    async def hop_job(hop):
        addr = _public(hop)
        info = await stat.network_info(addr)
        entry = {"prefix": None, "rpki": UNAVAILABLE}
        if info:
            entry["prefix"] = info["prefix"]
            origin = hop.get("asn") or (info["asns"][0] if info["asns"] else None)
            if not hop.get("asn") and info["asns"]:
                hop["asn"], hop["asn_source"] = info["asns"][0], "ripestat"
            if origin:
                entry["rpki"] = await stat.rpki(info["prefix"], origin) or UNAVAILABLE
        result["hops"][str(hop["hop"])] = entry
    await asyncio.gather(*(hop_job(h) for h in hops))

    # The AS path may have gained ASNs from RIPEstat.
    insight["as_path"] = osint.as_path(route)
    insight["as_path_text"] = osint.as_path_text(insight["as_path"])

    async def asn_job(asn):
        overview, neighbours = await asyncio.gather(stat.as_overview(asn), stat.as_neighbours(asn))
        result["asns"][str(asn)] = {"overview": overview, "neighbours": neighbours}
    await asyncio.gather(*(asn_job(p["asn"]) for p in insight["as_path"]))

    dest = _destination(route)
    if dest is None:
        result["errors"]["destination"] = "no public hop answered, so there is no destination prefix to ask about"
    else:
        prefix = (result["hops"].get(str(dest["hop"])) or {}).get("prefix")
        if not prefix:
            result["errors"]["destination"] = (
                "RIPEstat has no routed prefix for the last answering hop"
                + (f" ({stat.errors['network-info']})" if getattr(stat, "errors", {}).get("network-info") else ""))
        if prefix:
            paths, vis, window = await asyncio.gather(
                stat.ris_paths(prefix), stat.visibility(prefix), stat.bgp_update_window(prefix, end=now))
            updates = None if window is None else window["timestamps"]
            block = {"prefix": prefix, "visibility": vis, "ris": None, "updates": None}
            if paths is not None:
                dp = [p["asn"] for p in insight["as_path"]]
                block["ris"] = ripe.ris_agreement(dp, paths)
            if updates is not None:
                until = window["until"]
                block["updates"] = {"total": len(updates), "bins": ripe.hourly_bins(updates, now, until=until),
                                    "burst": ripe.update_burst(updates, now),
                                    "until": until.isoformat(timespec="minutes")}
            result["prefix"] = block
        result["baseline"] = await _baseline(route, dest, atlas)


async def _baseline(route, dest, atlas):
    origin = route.get("origin") or {}
    if origin.get("lat") is None or dest.get("lat") is None or dest.get("min_rtt_ms") is None:
        return None
    near = cities.nearest(origin["lat"], origin["lon"], max_km=400)
    origin_cc = (near or {}).get("cc")
    dest_cc = dest.get("cc")
    if not origin_cc or not dest_cc or origin_cc == dest_cc:
        return None
    value = await atlas.typical((origin["lat"], origin["lon"]), origin_cc,
                                (dest["lat"], dest["lon"]), dest_cc)
    if value is None:
        return {"unavailable": getattr(atlas, "error", None) or "RIPE Atlas gave no figure"}
    value["measured_ms"] = dest["min_rtt_ms"]
    return value


async def hop_details(hop: dict, settings: config.Settings, *, user_agent: str, sourceapp: str,
                      stat: ripe.RipeStat | None = None) -> dict:
    """RIR and abuse contacts for one hop, asked when the user opens its details."""
    addr = _public(hop)
    if not addr or not online_allowed(settings):
        return {"rir": None, "abuse": None, "status": OFF if addr else "local"}
    stat = stat or client(settings, user_agent, sourceapp)
    try:
        rir, abuse = await asyncio.wait_for(asyncio.gather(stat.rir(addr), stat.abuse(addr)), 12)
    except asyncio.TimeoutError:
        return {"rir": None, "abuse": None, "status": UNAVAILABLE}
    return {"rir": rir or UNAVAILABLE, "abuse": abuse if abuse is not None else UNAVAILABLE,
            "status": "done"}


def attributions(insight: dict | None) -> list[str]:
    """The credits an export must carry for what it shows."""
    out = []
    if insight and (insight.get("databases") or {}).get("asn") or (insight or {}).get("as_path"):
        out.append(f"{dbip.ATTRIBUTION} ({dbip.ATTRIBUTION_URL}, {dbip.LICENCE})")
    online = (insight or {}).get("online") or {}
    if online.get("status") not in (None, OFF):
        out.append("RIPE NCC RIPEstat (stat.ripe.net)")
        if isinstance(online.get("baseline"), dict):
            out.append("RIPE NCC RIPE Atlas (atlas.ripe.net), anchoring mesh")
    return out


# ---------------------------------------------------------------- summary ---
# What the panel and the PDF show, as plain values: one builder, two renderers.

RPKI_LABEL = {"valid": "RPKI valid", "unknown": "RPKI not found", "invalid": "RPKI invalid",
              "invalid_asn": "RPKI invalid (origin AS)", "invalid_length": "RPKI invalid (prefix length)"}
# The same states in a narrow column (hop table, PDF). "not found" is the RPKI
# term (RFC 6811) and the one used everywhere: badge, column, AS path, report.
RPKI_SHORT = {"valid": "valid", "unknown": "not found", "invalid": "INVALID", "invalid_asn": "INVALID",
              "invalid_length": "INVALID"}


def _rpki_badge(states: list[str]) -> dict | None:
    """One badge for every prefix seen in one AS: all valid, any invalid, or a count."""
    states = [s for s in states if s and s != UNAVAILABLE]
    if not states:
        return None
    if any(s.startswith("invalid") for s in states):
        bad = next(s for s in states if s.startswith("invalid"))
        return {"label": RPKI_LABEL[bad], "state": "invalid"}
    if all(s == "valid" for s in states):
        return {"label": "RPKI valid", "state": "valid"}
    valid = sum(1 for s in states if s == "valid")
    missing = sum(1 for s in states if s == "unknown")
    if valid == 0:
        return {"label": "RPKI not found", "state": "unknown"}
    return {"label": f"RPKI {valid} valid, {missing} not found", "state": "unknown"}


def summary(route: dict, ins: dict | None, origin_cc: str | None = None) -> dict:
    ins = ins or {}
    online = ins.get("online") or {}
    per_hop = online.get("hops") or {}
    hops_by_no = {h["hop"]: h for h in route.get("hops") or []}
    path = []
    for step in ins.get("as_path") or []:
        states = []
        seen = set()
        for n in step["hops"]:
            d = per_hop.get(str(n)) or {}
            if d.get("prefix") and d["prefix"] not in seen:
                seen.add(d["prefix"])
                states.append(d.get("rpki"))
        org = step.get("org") or ""
        holder = ((online.get("asns") or {}).get(str(step["asn"])) or {}).get("overview") or {}
        path.append({"asn": step["asn"], "org": org or holder.get("holder") or "",
                     "short": (org.split()[0].rstrip(",") if org else ""), "hops": step["hops"],
                     "rpki": _rpki_badge(states)})
    status = online.get("status")
    errors = online.get("errors") or {}
    out = {"as_path": path, "countries": ins.get("jurisdictions") or [], "origin_cc": origin_cc,
           "anycast": ins.get("anycast"), "status": status or "loading", "baseline": None,
           "ris": None, "updates": None, "reasons": {}}
    base = online.get("baseline")
    if isinstance(base, dict) and "unavailable" in base:
        out["baseline"] = UNAVAILABLE
        out["reasons"]["baseline"] = base["unavailable"]
    elif isinstance(base, dict):
        delta = base["measured_ms"] - base["ms"]
        # Name the trip, not the anchors' towns: the anchors stand for the two
        # countries, and their towns (an anchor in Makati, another in a village
        # near Bremen) read as if the route went there. They are in the detail.
        dest = _destination(route) or {}
        src = ((route.get("origin") or {}).get("label") or base["src"].get("city") or "").split(",")[0]
        dst = (dest.get("place") or base["dst"].get("city") or "").split(",")[0].split(" (")[0]
        out["baseline"] = {"text": f"typical {src} to {dst}: about {base['ms']:.0f} ms; "
                                   f"measured {base['measured_ms']:.0f} ms",
                           "delta": f"{delta:+.0f} ms",
                           "detail": f"RIPE Atlas anchor mesh, measurement {base['msm']}: "
                                     f"{base['src']['fqdn'].split('.')[0]} to {base['dst']['fqdn'].split('.')[0]}"}
    elif base == UNAVAILABLE:
        out["baseline"] = UNAVAILABLE
    prefix = online.get("prefix")
    if prefix:
        ris = prefix.get("ris")
        vis = prefix.get("visibility")
        lines = []
        if ris and ris.get("total"):
            origins = ", ".join(f"AS{a}" for a in ris.get("origin_asns") or [])
            asns = [p["asn"] for p in path]
            start = ris.get("compared_from")
            if start in asns:
                asns = asns[asns.index(start):]    # RIS peers never carry the access network
            via = " > ".join(f"AS{a}" for a in asns)
            if ris["agree"]:
                lines.append(f"origin {origins}; {ris['agree']} of {ris['total']} RIS peer paths "
                             f"carry {via} like this trace")
                others = ris["total"] - ris["agree"]
                parts = []
                for d in ris.get("diverge") or []:
                    if d["joins_at"] is None:
                        parts.append(f"{d['paths']} announced by a different origin")
                    elif d["via"] is None:
                        parts.append(f"{d['paths']} from route collectors that peer with AS{d['joins_at']} itself")
                    else:
                        parts.append(f"{d['paths']} reach AS{d['joins_at']} through AS{d['via']}"
                                     + (f" instead of AS{d['instead_of']}" if d.get("instead_of") else ""))
                if others and parts:
                    shown = sum(d["paths"] for d in ris.get("diverge") or [])
                    lines.append(f"the other {others}: " + "; ".join(parts)
                                 + (f"; {others - shown} more in smaller groups" if others > shown else ""))
                elif others:
                    lines.append(f"the other {others} take different paths; RIPEstat's answer does not say where "
                                 "they leave this one")
            elif ris.get("differs_at"):
                lines.append(f"origin {origins}; no RIS peer path matches this trace after "
                             f"AS{ris['differs_at']}: the forward path may differ from what BGP announces")
            else:
                lines.append(f"origin {origins}; {ris['total']} RIS peer paths, none through {via}")
        elif ris is None and status == "done":
            lines.append("RIS paths unavailable: " + errors.get("looking-glass", "RIPEstat gave no answer"))
        vis_text = (f"visible to {vis['seeing']} of {vis['total']} RIS peers" if vis else None)
        dest = _destination(route)
        rpki = (per_hop.get(str(dest["hop"])) or {}).get("rpki") if dest else None
        out["ris"] = {"prefix": prefix["prefix"], "lines": lines, "visibility": vis_text,
                      "rpki": _rpki_badge([rpki]) if rpki else None,
                      "low_visibility": bool(vis and vis["share"] < 0.8)}
        out["updates"] = prefix.get("updates")
        if out["updates"] is None:
            out["reasons"]["updates"] = errors.get("bgp-updates", "RIPEstat gave no answer")
        if vis is None:
            out["reasons"]["visibility"] = errors.get("routing-status", "RIPEstat gave no answer")
    elif status == "done":
        out["reasons"]["prefix"] = errors.get("destination", "no destination prefix was found")
    if (route.get("origin") or {}).get("source") != "supplied":
        out["reasons"]["origin"] = ("no origin was set for this trace, so there is no physics floor and the "
                                    "local hops have no place on the map (Settings > Origin)")
    return out
