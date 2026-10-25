"""The route summary for a path discovery: per path, never the merged table.

A discovery's hop table merges the routers of all its paths; the single-trace
summaries (the loss sentence, one AS path, one country list) run on it would
string paths together (AS12306 > AS1299 > AS12306) and lose the ones that
differ (France for the Marseille paths). Here each is worked out per path and
paths that agree are listed together.
"""
from __future__ import annotations

from routemap_engine import osint


def _groups(paths: list[dict], key) -> list[tuple[str, object]]:
    from routemap.gui.hoptable import letters
    order: list = []
    members: dict = {}
    for p in paths:
        k = key(p)
        if k not in members:
            order.append(k)
            members[k] = []
        members[k].append(p.get("id") or "?")
    return [(letters(members[k]), k) for k in order]


def as_paths(route: dict) -> list[tuple[str, list[dict]]]:
    """[(path letters, AS path)] for each distinct AS path, most paths first."""
    paths = (route.get("paths") or {}).get("paths") or []
    steps = {p.get("id"): osint.as_path({"hops": p.get("located") or []}) for p in paths}
    grouped = _groups(paths, lambda p: tuple((s["asn"], s["org"]) for s in steps[p.get("id")]))
    out = [(ids, [{"asn": a, "org": o} for a, o in key]) for ids, key in grouped if key]
    return sorted(out, key=lambda g: -len(g[0].split()))


def _chain(located: list[dict], sensitive: set[str], origin_cc: str | None = None) -> list[dict]:
    """A path's countries in order, with the hops between two different
    placed countries that have no place (no answer on this path, or nothing
    places the router) counted where they are: {"gap": n}. Without them
    "PH > DE" would read as one hop across the world."""
    out: list[dict] = []
    gap = 0
    for h in sorted(located, key=lambda h: h.get("hop") or 0):
        if h.get("source") == "local":
            continue
        cc = (h.get("cc") or "").upper() if h.get("lat") is not None else ""
        if not cc:
            gap += 1
            continue
        country_only = h.get("precision") == "country"
        if out and out[-1].get("cc") == cc:
            # Still in the same country: hops without a place in between hide
            # no crossing, so they are not shown.
            out[-1]["country_only"] = out[-1]["country_only"] and country_only
            gap = 0
            continue
        if gap and (out or (origin_cc and cc != origin_cc.upper())):
            out.append({"gap": gap})
        gap = 0
        out.append({"cc": cc, "country_only": country_only, "sensitive": cc in sensitive})
    return out


def countries(route: dict, sensitive: set[str] | frozenset = frozenset(),
              origin_cc: str | None = None) -> list[tuple[str, list[dict]]]:
    """[(path letters, countries transited)] for each distinct country list;
    an item is {"cc", "country_only", "sensitive"} or {"gap": hops without a
    place between two countries}."""
    sens = {c.upper() for c in sensitive}
    paths = (route.get("paths") or {}).get("paths") or []
    lists = {p.get("id"): _chain(p.get("located") or [], sens, origin_cc) for p in paths}
    grouped = _groups(paths, lambda p: tuple(tuple(sorted(c.items())) for c in lists[p.get("id")]))
    return [(ids, [dict(c) for c in key]) for ids, key in grouped if key]


def country_text(items: list[dict], origin_cc: str | None = None) -> str:
    """Plain text: "PH (origin) > PH > ... 4 hops without a place ... > DE"."""
    parts = [f"{origin_cc} (origin)"] if origin_cc else []
    for c in items:
        if "gap" in c:
            parts.append(f"... {c['gap']} hop{'s' if c['gap'] != 1 else ''} without a place ...")
        else:
            parts.append(c["cc"] + (" (country only)" if c["country_only"] else ""))
    return " > ".join(parts)


def target_summary(discovery: dict) -> str:
    """Per path, in the words of the path list: "10 of 10 answered: A C E J-M
    O P · 5 of 10 answered: B · not reached: D F-I N" (TCP), or loss to the
    target (ICMP: "0% loss: A B · 10% loss: C")."""
    from routemap.gui.hoptable import answered_none, letters
    paths = discovery.get("paths") or []
    tcp = discovery.get("method") == "tcp-paris"
    buckets: dict[str, list[str]] = {}
    for p in paths:
        if answered_none(p, discovery):
            label = f"0 of {p.get('sent')} answered" if tcp else "100% loss"
        elif not p.get("reached"):
            label = "not reached"
        elif not p.get("sent"):
            label = "not measured"
        elif tcp:
            label = f"{(p.get('sent') or 0) - (p.get('lost') or 0)} of {p.get('sent')} answered"
        else:
            label = f"{p.get('loss_pct') or 0:g}% loss"
        buckets.setdefault(label, []).append(p.get("id") or "?")

    def rank(label):
        if label == "not reached":
            return (2, 0)
        if label == "not measured":
            return (3, 0)
        n = label.split()[0].rstrip("%")
        return (0, -float(n)) if tcp else (0, float(n))
    parts = [f"{label}: {letters(ids)}" for label, ids in sorted(buckets.items(), key=lambda kv: rank(kv[0]))]
    return " · ".join(parts)
