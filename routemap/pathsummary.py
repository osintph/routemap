"""The route summary for a path discovery: per path, never the merged table.

A discovery's hop table merges every path's routers; the single-trace
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


def countries(route: dict, sensitive: set[str] | frozenset = frozenset()) -> list[tuple[str, list[dict]]]:
    """[(path letters, countries transited)] for each distinct country list."""
    paths = (route.get("paths") or {}).get("paths") or []
    lists = {p.get("id"): osint.jurisdictions({"hops": p.get("located") or []}, sensitive) for p in paths}
    grouped = _groups(paths, lambda p: tuple((c["cc"], c["country_only"], c["sensitive"]) for c in lists[p.get("id")]))
    return [(ids, [{"cc": c, "country_only": o, "sensitive": s} for c, o, s in key]) for ids, key in grouped if key]


def target_summary(discovery: dict) -> str:
    """Per path, in the words of the path list: "10 of 10 answered: A C E J-M
    O P · 5 of 10 answered: B · not reached: D F-I N" (TCP), or loss to the
    target (ICMP: "0% loss: A B · 10% loss: C")."""
    from routemap.gui.hoptable import letters
    paths = discovery.get("paths") or []
    tcp = discovery.get("method") == "tcp-paris"
    buckets: dict[str, list[str]] = {}
    for p in paths:
        if not p.get("reached"):
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
