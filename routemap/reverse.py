"""
Reverse traces via RIPE Atlas (0.4.0): a probe near the destination traces
back to this machine's public IP, and the two directions are compared.

Qt-free: the window and the CLI share it. Nothing here runs without the
user's consent to exactly what a reverse trace publishes: RIPE Atlas
measurements are public, and a reverse trace's target is the user's public
IP address. The consent text lives here, once, for the dialog, the CLI and
Help.

The probe is chosen by routemap_engine.atlas.select_reverse_probe: a connected
probe in the destination's AS, else its country, nearest the destination,
never in the user's own AS. One reverse trace costs atlas.TRACEROUTE_CREDITS (RIPE's
formula, checked in the engine's tests).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from routemap import config, policy, service
from routemap_engine import analyse, atlas, osint, whereami

TITLE = "Reverse traces publish your public IP address"
CREDITS = atlas.TRACEROUTE_CREDITS
AGREE = "I agree that reverse traces publish my public IP address as their target."
YOUR_IP_LABEL = "your public IP"


def consent_paragraphs(target: str, ip: str | None) -> list[str]:
    """The consent dialog's text, as approved for 0.4.0 (Phase 0, D1: public)."""
    now = f"now {ip}" if ip else "looked up when the trace starts"
    return [
        f"A reverse trace asks a RIPE Atlas probe near {target} to trace the route back to you.",
        "RIPE Atlas measurements are public. RIPE publishes each one in its public database, with the "
        "probe, the time, your Atlas account and the target. For a reverse trace, the target is your "
        f"public IP address, {now}. Anyone can look it up, and Route Map cannot remove it afterwards.",
        f"Each reverse trace costs {CREDITS} of your Atlas credits. Route Map sends RIPE Atlas the chosen "
        "probe and your public IP, nothing else; your origin coordinates are never sent.",
        "You can withdraw this at any time in Settings › RIPE Atlas.",
    ]


def consented(settings: config.Settings) -> bool:
    return bool(settings.reverse_consent_at)


def give_consent(settings: config.Settings, when: str) -> None:
    settings.reverse_consent_at = when
    config.save_settings(settings)


def withdraw_consent(settings: config.Settings) -> None:
    settings.reverse_consent_at = ""
    config.save_settings(settings)


class ReverseUnavailable(RuntimeError):
    """A reverse trace cannot run; the message says why and what to do."""


@dataclass
class Plan:
    af: int
    public_ip: str
    probe: dict
    dest_asn: int | None = None
    dest_cc: str | None = None
    dest_position: tuple[float, float] | None = None
    user_asn: int | None = None
    balance: object | None = None
    notes: list[str] = field(default_factory=list)


def destination(route: dict) -> dict | None:
    """The hop that is the destination: the last one with an address."""
    for hop in reversed(route.get("hops") or []):
        if hop.get("addresses") or hop.get("address"):
            return hop
    return None


def _offline_asn(addr: str) -> int | None:
    from routemap import insight
    reader = insight._asn_reader()
    rec = reader.lookup(addr) if reader is not None and addr else None
    return rec.asn if rec else None


def ready(settings: config.Settings) -> tuple[bool, str]:
    """Whether a reverse trace can be offered at all, and why not."""
    if not (settings.atlas_enabled and settings.atlas_key):
        return False, "Reverse traces use RIPE Atlas: turn it on and add your key in Settings › RIPE Atlas."
    if not (policy.RIPESTAT_ALLOWED and settings.online_lookups):
        return False, ("A reverse trace needs your public IP address from RIPEstat, and Online lookups "
                       "are off.")
    return True, ""


async def plan(route: dict, settings: config.Settings, *, transport=None) -> Plan:
    """Everything a reverse trace will use, before anything is created:
    the public IP of the traced family, the destination's network and the
    probe. Spends no credits."""
    ok, why = ready(settings)
    if not ok:
        raise ReverseUnavailable(why)
    dest = destination(route)
    if dest is None:
        raise ReverseUnavailable("No hop answered, so there is no destination to trace back from.")
    dest_addr = dest.get("address") or (dest.get("addresses") or [None])[0]
    af = 6 if ":" in (dest_addr or "") else 4
    ua = service.user_agent()
    try:
        ip = await whereami.public_ip(user_agent=ua, sourceapp=service.SOURCEAPP, family=af)
    except Exception as exc:  # noqa: BLE001
        raise ReverseUnavailable(f"Your public IPv{af} address could not be found ({exc}). "
                                 + ("Is IPv6 working on this network?" if af == 6 else "")) from exc
    dest_asn = dest.get("asn") or _offline_asn(dest_addr) or await whereami.asn_of(
        dest_addr, user_agent=ua, sourceapp=service.SOURCEAPP)
    user_asn = _offline_asn(ip) or await whereami.asn_of(ip, user_agent=ua, sourceapp=service.SOURCEAPP)
    pos = (dest["lat"], dest["lon"]) if dest.get("lat") is not None else None
    extra = {"transport": transport} if transport is not None else {}
    client = atlas.Atlas(settings.atlas_key, user_agent=ua, **extra)
    probe = await client.select_reverse_probe(dest_asn, dest.get("cc"), pos, user_asn=user_asn, af=af)
    balance = await client.balance()
    return Plan(af=af, public_ip=ip, probe=probe, dest_asn=dest_asn, dest_cc=dest.get("cc"),
                dest_position=pos, user_asn=user_asn, balance=balance)


async def run(p: Plan, settings: config.Settings, *, consent: bool, on_wait=None, transport=None,
              sources=None, agreed_for_this_run: bool = False) -> dict:
    """Create the measurement (only with *consent*), wait for it and place it.
    Returns the reverse block an export carries. The window needs the stored
    consent as well; the CLI never reads it and passes *agreed_for_this_run*
    when the user gave --publish-my-ip on that command."""
    if consent is not True or not (consented(settings) or agreed_for_this_run is True):
        raise ReverseUnavailable("A reverse trace publishes your public IP address. It needs your "
                                 "agreement first (Settings › RIPE Atlas).")
    extra = {"transport": transport} if transport is not None else {}
    client = atlas.Atlas(settings.atlas_key, user_agent=service.user_agent(), **extra)
    measurement = await client.create_reverse(p.public_ip, int(p.probe["id"]), consent=True)
    text = await client.wait(measurement, on_wait=on_wait)
    origin = (round(p.probe["lat"], 2), round(p.probe["lon"], 2)) if p.probe.get("lat") is not None else None
    route = await analyse(text, origin, sources=sources or service.sources_for(settings))
    route.target = YOUR_IP_LABEL
    if origin:
        route.origin["label"] = f"RIPE Atlas probe #{p.probe['id']} near {route.origin['label']}"
    return {"measurement_id": measurement, "af": p.af, "trace_text": text, "route": route,
            "probe": {k: p.probe.get(k) for k in ("id", "asn", "country", "distance_km", "lat", "lon")}}


def run_sync(p: Plan, settings: config.Settings, **kw) -> dict:
    return asyncio.run(run(p, settings, **kw))


# ------------------------------------------------------------- comparison ---

def _segments(hops: list[dict]) -> list[dict]:
    """Consecutive answering hops in one AS and one place, as one segment."""
    out: list[dict] = []
    for hop in hops:
        if not (hop.get("addresses") or hop.get("address")):
            continue
        asn = hop.get("asn")
        place = hop.get("place") or ("local" if hop.get("source") == "local" else None)
        key = (asn, place)
        if out and out[-1]["key"] == key:
            out[-1]["hops"].append(hop)
            continue
        out.append({"key": key, "asn": asn, "place": place, "hops": [hop]})
    return out


def _lcs(a: list, b: list, same) -> list[tuple[int, int]]:
    n, m = len(a), len(b)
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            table[i][j] = table[i + 1][j + 1] + 1 if same(a[i], b[j]) else max(table[i + 1][j], table[i][j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if same(a[i], b[j]):
            pairs.append((i, j))
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def compare(forward: dict, reverse_route: dict) -> dict:
    """Forward and reverse side by side, aligned by network, not by hop number.

    The reverse route runs from the probe to the user; it is read backwards so
    both columns go from the user to the target. Segments (consecutive hops in
    one AS and one place) are aligned by the longest common sequence of
    (AS, place); everything between two aligned segments is where the two
    directions differ. Returns {"rows": [...], "differs": bool, "summary": str,
    "split_rejoin": [(forward segment, reverse segment), ...]}.
    """
    fwd = _segments(forward.get("hops") or [])
    rev = _segments(list(reversed(reverse_route.get("hops") or [])))

    def same(x, y):
        if x["place"] == "local" and y["place"] == "local":
            return True
        return x["asn"] is not None and x["asn"] == y["asn"] and x["place"] == y["place"]

    pairs = _lcs(fwd, rev, same)
    rows, i, j = [], 0, 0
    for pi, pj in pairs + [(len(fwd), len(rev))]:
        gap_f, gap_r = fwd[i:pi], rev[j:pj]
        for k in range(max(len(gap_f), len(gap_r))):
            rows.append({"forward": gap_f[k] if k < len(gap_f) else None,
                         "reverse": gap_r[k] if k < len(gap_r) else None, "same": False})
        if pi < len(fwd):
            rows.append({"forward": fwd[pi], "reverse": rev[pj], "same": True})
        i, j = pi + 1, pj + 1
    differs = any(not r["same"] for r in rows)
    return {"rows": rows, "differs": differs, "summary": _summary(rows)}


def _where(seg: dict | None) -> str:
    if seg is None:
        return ""
    return seg["place"] if seg["place"] and seg["place"] != "local" else (
        f"AS{seg['asn']}" if seg["asn"] else "an unplaced hop")


def _summary(rows: list[dict]) -> str:
    if not rows:
        return "Neither direction has an answering hop to compare."
    if all(r["same"] for r in rows):
        return "Both directions go through the same networks and places."
    first = next(i for i, r in enumerate(rows) if not r["same"])
    last = max(i for i, r in enumerate(rows) if not r["same"])
    before = next((rows[i]["forward"] for i in range(first - 1, -1, -1) if rows[i]["same"]), None)
    after = next((rows[i]["forward"] for i in range(last + 1, len(rows)) if rows[i]["same"]), None)
    fwd = [_where(r["forward"]) for r in rows[first:last + 1] if r["forward"]]
    rev = [_where(r["reverse"]) for r in rows[first:last + 1] if r["reverse"]]
    span = (f"between {_where(before)} and {_where(after)}" if before and after else
            f"after {_where(before)}" if before else f"before {_where(after)}" if after else "throughout")
    def via(parts):
        parts = [p for i, p in enumerate(parts) if p and p not in parts[:i]]
        return " and ".join(parts) if parts else "no answering hop"
    return f"The paths differ {span}: forward goes via {via(fwd)}, reverse via {via(rev)}."


def enrich(route: dict) -> dict:
    """Offline ASNs on *route*'s hops (in place), as the forward route has them."""
    from routemap import insight
    reader = insight._asn_reader()
    if reader is not None:
        osint.enrich_offline(route, reader)
    return route
