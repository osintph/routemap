"""
Continuous mode, the app's side: Qt-free, shared by the window and the CLI.

The engine (routemap_engine.watch) probes and counts. This module turns its
session into what the app shows and saves:

* :func:`snapshot` copies what the window needs after a cycle, in the probing
  thread, so the window never reads a session that is being written.
* :func:`merge_hops` lays the running figures over the placed route: the map
  keeps the placements from the first cycle, and the table shows the mtr
  columns with the 0.5.0 loss rule applied to the session's own loss.
* :func:`route_for_export` is the route a compare or an export uses: the
  session's average as the hop's RTT and the session's loss as its loss.
* :func:`table_text` is the mtr-style table the CLI prints.
"""
from __future__ import annotations

import copy

from routemap_engine import geo, watch
from routemap_engine.parse import Hop

STAT_KEYS = ("sent", "received", "loss_pct", "last_ms", "best_ms", "avg_ms", "worst_ms", "stdev_ms")

# What Settings shows; the engine enforces them.
INTERVAL_MIN = watch.INTERVAL_MIN
INTERVAL_MAX = watch.INTERVAL_MAX
DURATION_MIN = watch.DURATION_MIN
DURATION_MAX = watch.DURATION_MAX
MAX_RATE = watch.MAX_RATE
WAIT = watch.WAIT


def snapshot(session: watch.Session, paused: bool = False) -> dict:
    """Everything the window draws after a cycle, as plain data."""
    hops = session.hops()
    return {
        "target": session.target, "address": session.address,
        "cycles": session.cycles, "started": session.started_wall,
        "interval": session.options.interval, "duration": session.options.duration,
        "reached_hop": session.reached_hop, "hops": hops, "loss": geo.loss_verdict(hops),
        "changes": [dict(c) for c in session.changes], "gaps": [dict(g) for g in session.gaps],
        "resets": list(session.resets), "stopped_by": session.stopped_by, "paused": paused,
        "live": {n: list(s.live) for n, s in session.samples.items()},
    }


def as_hops(hops: list[dict]) -> list[Hop]:
    """Session hop dicts as parser Hops, for placing them."""
    return [Hop(hop=h["hop"], addresses=list(h.get("addresses") or []),
                rtts_ms=[] if h.get("best_ms") is None else [h["best_ms"]],
                sent=h.get("sent") or 0, lost=(h.get("sent") or 0) - (h.get("received") or 0))
            for h in hops if h.get("addresses")]


def unplaced(snap_hops: list[dict], route_hops: list[dict]) -> list[Hop]:
    """Hops or addresses the placed route does not have: the only ones to place."""
    placed = {h["hop"]: set(h.get("addresses") or []) for h in route_hops}
    out = []
    for h in as_hops(snap_hops):
        missing = [a for a in h.addresses if a not in placed.get(h.hop, set())]
        if missing:
            out.append(Hop(hop=h.hop, addresses=missing, rtts_ms=list(h.rtts_ms), sent=h.sent, lost=h.lost))
    return out


def add_placed(route_hops: list[dict], placed: list[dict]) -> list[dict]:
    """Merge newly placed hop entries into the route: a new hop is added, an
    existing one only gains the new addresses. Earlier placements never move."""
    by_hop = {h["hop"]: h for h in route_hops}
    for entry in placed:
        mine = by_hop.get(entry["hop"])
        if mine is None:
            by_hop[entry["hop"]] = copy.deepcopy(entry)
            continue
        for a in entry.get("addresses") or []:
            if a not in (mine.get("addresses") or []):
                mine.setdefault("addresses", []).append(a)
    return [by_hop[n] for n in sorted(by_hop)]


def merge_hops(route_hops: list[dict], snap_hops: list[dict]) -> list[dict]:
    """The placed route's hops with the session's figures laid over them, one
    row per hop the session probed. Loss annotations come from the session."""
    placed = {h["hop"]: h for h in route_hops}
    out = []
    for s in snap_hops:
        base = copy.deepcopy(placed.get(s["hop"]) or {"hop": s["hop"], "addresses": [], "lat": None,
                                                     "lon": None, "source": "unresolved",
                                                     "annotations": []})
        for a in s.get("addresses") or []:
            if a not in (base.get("addresses") or []):
                base.setdefault("addresses", []).append(a)
        if not base.get("address") and base.get("addresses"):
            base["address"] = base["addresses"][0]
        for k in STAT_KEYS:
            base[k] = s.get(k)
        base["min_rtt_ms"] = s.get("best_ms")
        base["avg_rtt_ms"] = s.get("avg_ms")
        base["loss_pct"] = s.get("loss_pct")
        notes = [a for a in base.get("annotations") or [] if a != geo.ANNOT_ICMP_LIMIT]
        if geo.ANNOT_ICMP_LIMIT in (s.get("annotations") or []):
            notes.append(geo.ANNOT_ICMP_LIMIT)
        base["annotations"] = notes
        out.append(base)
    return out


def route_for_export(route: dict, snap: dict) -> dict:
    """The route a compare or an export uses: placements from the session's
    route, RTT and loss from the session's figures."""
    body = copy.deepcopy(route)
    body["hops"] = merge_hops(route.get("hops") or [], snap["hops"])
    return body


def session_document(session_dict: dict) -> dict:
    """The ``session`` section of an export (format version 3)."""
    return copy.deepcopy(session_dict)


def label(hop: dict) -> str:
    return hop.get("place") or hop.get("address") or (hop.get("addresses") or ["?"])[0]


def table_text(snap: dict, places: dict[int, str] | None = None) -> str:
    """The mtr-style table the CLI prints."""
    places = places or {}
    rows = [" #  Host                          Loss%   Snt    Last     Avg    Best    Wrst   StDev"]

    def f(v, w=7):
        return f"{v:{w}.1f}" if v is not None else " " * (w - 1) + "?"
    limited = False
    for h in snap["hops"]:
        name = places.get(h["hop"]) or (h["addresses"][0] if h["addresses"] else "???")
        loss = h.get("loss_pct")
        mark = "*" if geo.ANNOT_ICMP_LIMIT in (h.get("annotations") or []) else " "
        limited = limited or mark == "*"
        loss_text = "  ?  " if loss is None else f"{loss:5.1f}"
        rows.append(f"{h['hop']:>2}  {name[:28]:<28}  {loss_text}{mark} {h['sent']:>4} {f(h['last_ms'])} "
                    f"{f(h['avg_ms'])} {f(h['best_ms'])} {f(h['worst_ms'])} {f(h['stdev_ms'])}")
    notes = []
    if limited:
        notes.append("* ICMP rate limiting at this hop, not real loss.")
    changes = snap.get("changes") or []
    notes.append(f"Path changes: {len(changes)}." if changes else "Path changes: none.")
    if snap.get("gaps"):
        notes.append(f"Gaps (sleep or suspend, not counted): {len(snap['gaps'])}.")
    return "\n".join(rows + [" ".join(notes)])


def describe_change(change: dict) -> str:
    """One sentence for the change list, the PDF and screen readers."""
    hop, kind = change.get("hop"), change.get("kind")
    old = ", ".join(change.get("old") or []) if isinstance(change.get("old"), list) else change.get("old")
    new = ", ".join(change.get("new") or []) if isinstance(change.get("new"), list) else change.get("new")
    if kind == "appeared":
        what = f"hop {hop} started answering, from {new}"
    elif kind == "disappeared":
        what = f"hop {hop} stopped answering (was {old})"
    elif kind == "destination":
        what = f"the destination is now hop {new} (was hop {old})"
    else:
        what = f"hop {hop} answered from {new} instead of {old}"
    return f"Cycle {change.get('cycle')}: {what}."


def _epoch(iso) -> float | None:
    import datetime as _dt
    if not isinstance(iso, str):
        return None
    try:
        return _dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def saved_snapshot(session: dict) -> dict:
    """A stored or opened session (rebuilt by routemap.imported.session) as a
    snapshot the window draws: stopped, with the plot made from the raw
    samples and, past them, the one-minute buckets' means."""
    live = {}
    samples = (session.get("samples") or {}).get("hops") or {}
    raw_seconds = (session.get("samples") or {}).get("raw_seconds") or 1800
    for key, value in samples.items():
        points = [(t, r) for t, r in value.get("raw") or []]
        last = points[-1][0] if points else -1
        for b in value.get("buckets") or []:
            if b["t"] >= raw_seconds and b["t"] > last:
                mean = b.get("mean_ms")
                points.append((b["t"], mean))
        live[int(key)] = points
    started = _epoch(session.get("started")) or 0.0
    changes = [dict(c, at=_epoch(c.get("at"))) for c in session.get("changes") or []]
    gaps = [{"from": _epoch(g.get("from")), "to": _epoch(g.get("to"))} for g in session.get("gaps") or []]
    hops = session.get("hops") or []
    return {"target": session.get("target"), "address": session.get("address"),
            "cycles": session.get("cycles", 0), "started": started, "now": _epoch(session.get("ended")) or started,
            "interval": session.get("interval_s") or 1.0, "duration": session.get("duration_limit_s") or 3600.0,
            "reached_hop": session.get("reached_hop"), "hops": hops,
            "loss": session.get("loss") or geo.loss_verdict(hops),
            "changes": changes, "gaps": [g for g in gaps if g["from"] is not None and g["to"] is not None],
            "resets": session.get("resets") or [], "stopped_by": session.get("stopped_by") or "user",
            "paused": False, "live": live}
