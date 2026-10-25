"""
DNS timing and port tests for a trace (0.5.0-beta.1), and the words every
view uses for them and for the Paths header. Qt-free: the window, the CLI,
the PDF and the PNG all read these.

Where things go: DNS lookups to the system resolver and to the resolvers in
Settings > Probes (none by default), nowhere else; port tests to the traced
address only. See routemap_engine.dnstime and routemap_engine.ports.
"""
from __future__ import annotations

from routemap_engine import dnstime, ports as engine_ports


def resolve(target: str, settings) -> dict:
    """The address to trace, resolved once; the one every view shows."""
    return dnstime.resolve_target(target, settings.ip_version).to_dict()


def measure_dns(target: str, settings, *, system: bool = True) -> list[dict]:
    """The DNS timing rows. The resolvers in Settings > Probes are asked only
    while Online lookups is on (Help > Privacy lists them under it); the
    system resolver is the one the trace needs anyway."""
    named = settings.dns_resolvers if getattr(settings, "online_lookups", True) else []
    return [r.to_dict() for r in dnstime.measure(target, named, system=system)]


def check_ports(address: str, target: str, settings, ports=None) -> dict:
    return engine_ports.check_ports(address, ports if ports is not None else settings.port_list,
                                    tls_ports=settings.tls_ports, wait=settings.port_wait,
                                    server_name=target).to_dict()


def _ms(value) -> str:
    if value is None:
        return ""
    return f"{value:.0f} ms" if value >= 10 else f"{value:.1f} ms"


def system_row(dns: list[dict] | None, family: int | None) -> dict | None:
    kind = "AAAA" if family == 6 else "A"
    return next((r for r in dns or [] if r.get("resolver") == dnstime.SYSTEM and r.get("type") == kind), None)


def dns_line(resolved: dict | None, dns: list[dict] | None, *, where: str = "system resolver") -> str:
    """'bbc.com resolved to 151.101.0.81 in 18 ms (system resolver)'."""
    if not resolved:
        return ""
    name, address = resolved.get("name"), resolved.get("address")
    if resolved.get("by") == "literal" or name == address:
        return f"Traced address {address}"
    row = system_row(dns, resolved.get("family"))
    took = f" in {_ms(row['ms'])}" if row and row.get("ms") is not None else ""
    return f"{name} resolved to {address}{took} ({where})"


def ports_line(ports: dict | None) -> str:
    """'ports: 443 open 9 ms, 80 open, 22 filtered'."""
    if not ports or not ports.get("results"):
        return ""
    parts = []
    for i, r in enumerate(ports["results"]):
        if r["state"] == "filtered":
            continue
        cell = f"{r['port']} {r['state']}"
        if r["state"] == "open" and i == 0 and r.get("connect_ms") is not None:
            cell += f" {_ms(r['connect_ms'])}"
        parts.append(cell)
    filtered = sum(1 for r in ports["results"] if r["state"] == "filtered")
    if filtered:
        parts.append(f"{filtered} filtered" if parts else f"all {filtered} filtered")
    return "ports: " + ", ".join(parts)


DNS_HEADERS = ["Resolver", "Type", "Time", "Answer", "Authoritative", "Cached", "TTL", "Addresses"]


def dns_rows(dns: list[dict] | None) -> list[list[str]]:
    rows = []
    for r in dns or []:
        system = r.get("resolver") == dnstime.SYSTEM
        if r.get("error"):
            answer = r["error"]
        elif system:
            n = len(r.get("addresses") or [])
            answer = f"{n} address{'es' if n != 1 else ''}"
        else:
            answer = r.get("rcode") or ""
        aa = "not stated" if r.get("aa") is None else ("yes" if r["aa"] else "no")
        rows.append(["System resolver" if system else r.get("resolver") or "", r.get("type") or "",
                     _ms(r.get("ms")) if r.get("ms") is not None else "", answer, aa, "not stated",
                     "" if r.get("ttl") is None else f"{r['ttl']} s", ", ".join(r.get("addresses") or [])])
    return rows


def dns_note(resolved: dict | None) -> str:
    if not resolved:
        return ""
    return (f"Traced: {resolved.get('address')}. Time is from the query leaving this computer to the first "
            "answer. A resolver that does not say whether it answered from its cache shows \"not stated\".")


PORT_HEADERS = ["Port", "Result", "Connect", "TLS handshake"]


def port_rows(ports: dict | None) -> list[list[str]]:
    rows = []
    for r in (ports or {}).get("results") or []:
        result = r["state"] + (f" ({r['reason']})" if r.get("reason") and r["state"] != "open" else "")
        tls = _ms(r.get("tls_ms")) if r.get("tls_ms") is not None else (r.get("tls_error") or "")
        rows.append([str(r["port"]), result, _ms(r.get("connect_ms")) if r.get("connect_ms") is not None else "",
                     tls])
    return rows


def ports_title(ports: dict | None) -> str:
    if not ports:
        return "Ports"
    results = ports.get("results") or []
    opened = sum(1 for r in results if r["state"] == "open")
    return (f"Ports: {len(results)} tested to {ports.get('address')}, {opened} open"
            + (f" · {ports['seconds']:g} s" if ports.get("seconds") is not None else ""))


def ports_note(ports: dict | None, *, where: str = "this computer") -> str:
    if not ports:
        return ""
    note = (f"From {where}. One connection attempt per port, at most {ports.get('cap', 32)} ports, "
            f"{ports.get('parallel', 4)} at a time: a reachability check for one target, not a port scanner. "
            "Filtered means nothing answered: a firewall on the way, at the target, or on your own network "
            "(many ISPs block outgoing port 25).")
    used, wait = ports.get("wait_used"), ports.get("wait")
    if used is not None and wait is not None and used < wait - 0.25:
        note += (f" The system gave up on unanswered ports after about {used:g} s, not the {wait:g} s "
                 "set in Settings (Windows sends one connection attempt and waits for its first "
                 "retransmission timer).")
    return note


# ------------------------------------------------------------- Paths header

def paths_lines(disc: dict | None, *, trace_resolved: dict | None = None, ports: dict | None = None) -> list[str]:
    """What a path discovery's heading says beyond its counts (0.5.0-beta.1):
    the address traced (and the Trace's, when it differs), why discovery
    ended, what the full-TTL attempts found, and TCP silence."""
    if not disc:
        return []
    out = []
    resolved = disc.get("resolved") or {}
    if resolved.get("address"):
        line = (f"{resolved.get('name')} resolved to {resolved['address']}" if resolved.get("name") not in
                (None, resolved["address"]) else f"Traced address {resolved['address']}")
        other = (trace_resolved or {}).get("address")
        if other and other != resolved["address"] and (trace_resolved or {}).get("name") == resolved.get("name"):
            line += f" (Trace resolved {other})"
        out.append(line)
    paths = disc.get("paths") or []
    late = [p for p in paths if p.get("reached_by") == "full_ttl"]
    if disc.get("stopped_by") == "gap" and disc.get("silent_stop"):
        a, b = disc["silent_stop"]
        line = f"Discovery stopped after {b - a + 1} silent hops ({a} to {b})."
        if paths:
            reached = sum(1 for p in paths if p.get("reached"))
            line += (" The target was then asked at full TTL: " +
                     (f"reached on all {len(paths)} paths found." if reached == len(paths) else
                      ("not reached." if not reached else f"reached on {reached} of {len(paths)} paths.")))
        out.append(line)
    elif disc.get("stop_text") and disc.get("stopped_by") not in ("complete", None):
        out.append(f"Discovery {disc['stop_text']}.")
    if disc.get("tcp_silent_from"):
        n = disc["tcp_silent_from"]
        if disc.get("tcp_silent_by") == "target":
            out.append(f"The target answers ICMP at hop {n} but its TCP service answered only at full TTL; "
                       "a firewall or load balancer in front of the target is likely.")
        else:
            out.append(f"Routers on this network do not answer TCP probes beyond hop {n - 1}; Paths cannot map "
                       "past it here; Trace (ICMP) can.")
    short = [p for p in late if (p.get("sent") or 0) and (p.get("lost") or 0)]
    if len(short) == 1:
        p = short[0]
        out.append(f"Path {p.get('id')}: the target answered {p['sent'] - p['lost']} of {p['sent']} attempts; "
                   "some servers answer fewer after the discovery's probes.")
    elif short:
        got = sorted(p["sent"] - p["lost"] for p in short)
        sent = max(p["sent"] for p in short)
        span = f"{got[0]}" if got[0] == got[-1] else f"{got[0]} to {got[-1]}"
        out.append(f"On {len(short)} paths the target answered {span} of {sent} attempts each; some servers "
                   "answer fewer after the discovery's probes.")
    unreached = [p for p in paths if not p.get("reached")]
    if unreached and ports and ports.get("address") == resolved.get("address"):
        port = next((r for r in ports.get("results") or [] if r["port"] == (disc.get("port") or 443)), None) \
            or next(iter(ports.get("results") or []), None)
        if port and port["state"] == "open":
            out.append(f"Port {port['port']} answered (open, {_ms(port.get('connect_ms'))}): the target is up; "
                       "the routers in between do not answer.")
        elif port:
            out.append(f"Port {port['port']} did not answer either ({port['state']}).")
    return out
