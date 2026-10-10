"""Everything the app reads back from a file is rebuilt here before it is shown
(RM-01, hardening 3): route exports (opened or compared) and history entries.

An export or a history file is someone else's text until proven otherwise: a
colleague's export, a file from a ticket, a history file another program wrote.
So nothing in it is used as it stands. The route is rebuilt from the engine's
own route.schema.json: only the fields the schema knows survive, each coerced
to its type and range, text is plain and capped, addresses must parse as
addresses and hostnames as hostnames, and the parser label is taken from the
parser, not from the file. The saved insight is dropped and computed again.
Files larger than MAX_FILE_BYTES are refused before they are read (RM-12).
A continuous session (format version 3) is rebuilt the same way by
:func:`session`: every count, time and RTT checked, every list capped.
"""
from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import unicodedata
from functools import lru_cache
from importlib import resources

from routemap_engine.parse import PARSER_LABELS

# 8 MB: an 8-hour continuous session with its plot data is about 4 MB (RM-12).
MAX_FILE_BYTES = 8_000_000
MAX_TEXT = 300
FORMAT_VERSION = 4            # the newest export this version reads (service.EXPORT_FORMAT_VERSION)
MAX_ITEMS = 512
MAX_TRACE_TEXT = 256_000
SOURCES = ("local", "paste", "file", "atlas", "watch", "paths")
ORIGIN_HOWS = ("auto", "city", "coords", "map", "ip")
_HOSTNAME = re.compile(r"[A-Za-z0-9_.:-]{1,253}")
_WHEN = re.compile(r"\d{4}-\d\d-\d\dT[\d:.]+(?:Z|[+-]\d\d:?\d\d)?")


# No value Route Map writes comes near these: a number past them, a NaN or an
# infinity is a malformed file, refused with its place named, so it can never
# reach Qt as a value it cannot hold (an int past 64 bits, a float overflow).
MAX_NUMBER = 1e9
NUMBER_LIMITS = {"asn": 2**32 - 1}


class ImportRejected(ValueError):
    """The file is not something the app will show."""


class NewerFormat(ImportRejected):
    """A real export, from a newer Route Map. Shown with its own title, not as
    "not a routemap export"."""

    TITLE = "Made by a newer Route Map"

    def __init__(self, version: int):
        self.version = version
        self.title = self.TITLE
        self.message = (f"This export is format version {version}, made by a newer Route Map. "
                        f"This Route Map opens format {FORMAT_VERSION} and older. Update Route Map to open it.")
        super().__init__(self.message)


def parse_json(text: str):
    """json.loads that refuses NaN and Infinity, and a file nested deeper than
    the parser can follow (RecursionError), as ImportRejected."""
    def constant(name):
        raise ImportRejected(f"the file holds {name}, which is not a number")
    try:
        return json.loads(text, parse_constant=constant)
    except RecursionError:
        raise ImportRejected("the file is nested too deeply to be a route export") from None


def read_file(path: str) -> str:
    """The file's text, or ImportRejected when it is larger than any real export."""
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise ImportRejected(str(exc)) from exc
    if size > MAX_FILE_BYTES:
        raise ImportRejected(f"the file is {size // 1000} KB; a route export is smaller "
                             f"(at most {MAX_FILE_BYTES // 1_000_000} MB)")
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read(MAX_FILE_BYTES + 1)


def text(value, limit: int = MAX_TEXT, *, newlines: bool = False) -> str | None:
    """A string without control characters, at most *limit* long, or None."""
    if not isinstance(value, str):
        return None
    keep = "\n\t" if newlines else ""
    cleaned = "".join(ch for ch in value[: limit * 2]
                      if ch in keep or unicodedata.category(ch)[0] != "C")
    return cleaned[:limit] or None


@lru_cache(maxsize=1)
def _schema() -> dict:
    return json.loads(resources.files("routemap_engine").joinpath("route.schema.json").read_text("utf-8"))


_DROP = object()


def _resolve(node: dict) -> dict:
    ref = node.get("$ref")
    if ref:
        name = ref.rsplit("/", 1)[-1]
        defs = _schema().get("$defs") or _schema().get("definitions") or {}
        return {**defs[name], **{k: v for k, v in node.items() if k != "$ref"}}
    return node


def _field(key: str, value):
    """Checks beyond the schema's types, for the fields that name things."""
    if key in ("address",):
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            return _DROP
    if key in ("hostname",):
        return value if _HOSTNAME.fullmatch(value) else _DROP
    if key == "cc":
        return value.upper() if re.fullmatch(r"[A-Za-z]{2}", value) else None
    if key == "hoiho_ruleset_date":
        return value if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value) else None
    if key == "as_network":
        try:
            return str(ipaddress.ip_network(value, strict=False))
        except ValueError:
            return None
    return value


def _number(value, node: dict, where: str):
    """A number within the schema's range and below MAX_NUMBER, or ImportRejected."""
    key = where.rsplit(".", 1)[-1]
    try:
        size = abs(float(value))
    except OverflowError:
        size = float("inf")
    limit = NUMBER_LIMITS.get(key, MAX_NUMBER)
    low, high = node.get("minimum", -limit), node.get("maximum", limit)
    if not math.isfinite(size) or size > limit or not low <= value <= high:
        if not math.isfinite(size):
            raise ImportRejected(f"{where} is larger than any number a route holds")
        raise ImportRejected(f"{where} is {value:.3g}, outside what a route holds")
    return value


def _coerce(value, node: dict, key: str = "", where: str = "route"):
    node = _resolve(node)
    types = node.get("type")
    types = [types] if isinstance(types, str) else list(types or [])
    if "enum" in node:
        if value in node["enum"]:
            return value
        return None if None in node["enum"] or "null" in types else _DROP
    if value is None:
        return None if "null" in types else _DROP
    if isinstance(value, bool):
        return value if "boolean" in types else _DROP
    if isinstance(value, (int, float)) and ("integer" in types or "number" in types):
        value = _number(value, node, where)
        if "integer" in types and "number" not in types:
            if isinstance(value, float) and not value.is_integer():
                return _DROP
            value = int(value)
        return value
    if isinstance(value, str) and "string" in types:
        cleaned = text(value, node.get("maxLength", MAX_TEXT))
        if cleaned is None:
            return None if "null" in types else _DROP
        return _field(key, cleaned)
    if isinstance(value, list) and "array" in types:
        item = node.get("items") or {}
        out = []
        for i, v in enumerate(value[:min(MAX_ITEMS, node.get("maxItems", MAX_ITEMS))]):
            c = _coerce(v, item, {"addresses": "address", "hostnames": "hostname"}.get(key, key), f"{where}[{i}]")
            if c is not _DROP:
                out.append(c)
        return out
    if isinstance(value, dict) and "object" in types:
        props = node.get("properties") or {}
        if "lat" in props and "lon" in props and (value.get("lat") is None) != (value.get("lon") is None):
            raise ImportRejected(f"{where} has a latitude or a longitude without the other")
        out = {}
        for k, sub in (node.get("properties") or {}).items():
            if k in value:
                c = _coerce(value[k], sub, k, f"{where}.{k}")
                if c is not _DROP:
                    out[k] = c
        missing = [k for k in node.get("required") or [] if k not in out]
        return _DROP if missing else out
    return _DROP


def route(data) -> dict:
    """The route in *data*, rebuilt from the schema, or ImportRejected."""
    if not isinstance(data, dict):
        raise ImportRejected("no route in the file")
    rebuilt = _coerce(data, _schema())
    if rebuilt is _DROP or not isinstance(rebuilt, dict) or not rebuilt.get("hops"):
        raise ImportRejected("the file's route does not match the route format")
    # A route placed from a list of hops (a continuous session) has the
    # engine's parser "hops", which the text parsers' labels do not name.
    rebuilt["parser_label"] = PARSER_LABELS.get(rebuilt.get("parser")) or (
        "hops" if rebuilt.get("parser") == "hops" else "")
    target = rebuilt.get("target")
    rebuilt["target"] = _target(target)
    return rebuilt


def _target(value) -> str | None:
    """The target as display text. It is a label as often as a host ("pasted
    trace", a file name); tracing it again goes through validate_target first."""
    return text(value, 253)


def argv(value) -> list[str] | None:
    if not isinstance(value, list):
        return None
    out = [t for t in (text(v, 256) for v in value[:64]) if t]
    return out or None


# ------------------------------------------------------------------ session ---

SESSION_HOPS = 30
SESSION_CHANGES = 1000
SESSION_GAPS = 1000
SESSION_RAW = 1800 * 2           # raw samples per hop (30 minutes at the 1 s floor), with slack
SESSION_BUCKETS = 8 * 60 + 10    # one-minute buckets over the 8-hour maximum
CHANGE_KINDS = ("address", "appeared", "disappeared", "destination")
STOPPED_BY = ("user", "duration", "count", "error")


def _num(value, low: float, high: float):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value if low <= value <= high else None


def _int(value, low: int, high: int):
    v = _num(value, low, high)
    return int(v) if v is not None and float(v).is_integer() else None


def _ms(value):
    return _num(value, 0, 600_000)


def _iso(value):
    return value if isinstance(value, str) and _WHEN.fullmatch(value[:40]) else None


def _address(value) -> str | None:
    """An IP address given as text; ip_address() would also take an integer."""
    if not isinstance(value, str):
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _addresses(value) -> list[str]:
    out = []
    for a in (value if isinstance(value, list) else [])[:16]:
        if not isinstance(a, str):
            continue
        try:
            out.append(str(ipaddress.ip_address(a)))
        except (ValueError, TypeError):
            continue
    return out


def session(data) -> dict | None:
    """A continuous session rebuilt from a file, or None when it is not one."""
    if not isinstance(data, dict):
        return None
    address = _address(data.get("address"))
    if address is None:
        return None
    hops = []
    for h in (data.get("hops") if isinstance(data.get("hops"), list) else [])[:SESSION_HOPS]:
        if not isinstance(h, dict) or _int(h.get("hop"), 1, 255) is None:
            continue
        sent = _int(h.get("sent"), 0, 10**7)
        received = _int(h.get("received"), 0, 10**7)
        if sent is None or received is None or received > sent:
            continue
        hops.append({"hop": int(h["hop"]), "addresses": _addresses(h.get("addresses")),
                     "sent": sent, "received": received,
                     "loss_pct": _num(h.get("loss_pct"), 0, 100),
                     "last_ms": _ms(h.get("last_ms")), "best_ms": _ms(h.get("best_ms")),
                     "avg_ms": _ms(h.get("avg_ms")), "worst_ms": _ms(h.get("worst_ms")),
                     "stdev_ms": _ms(h.get("stdev_ms")), "annotations": []})
    hops.sort(key=lambda h: h["hop"])
    # The loss rule is computed again here, from the file's own figures.
    from routemap_engine import geo
    for h in hops:
        h["min_rtt_ms"] = h["best_ms"]
    geo.annotate(hops)
    for h in hops:
        h.pop("min_rtt_ms", None)
    changes = []
    for c in (data.get("changes") if isinstance(data.get("changes"), list) else [])[:SESSION_CHANGES]:
        if not isinstance(c, dict) or c.get("kind") not in CHANGE_KINDS:
            continue
        cycle = _int(c.get("cycle"), 0, 10**7)
        hop = _int(c.get("hop"), 0, 255)
        if cycle is None or hop is None:
            continue
        def side(v):
            return _int(v, 0, 255) if c.get("kind") == "destination" else _addresses(v)
        changes.append({"cycle": cycle, "confirmed_cycle": _int(c.get("confirmed_cycle"), 0, 10**7) or cycle,
                        "at": _iso(c.get("at")), "hop": hop, "kind": c["kind"],
                        "old": side(c.get("old")), "new": side(c.get("new"))})
    gaps = []
    for g in (data.get("gaps") if isinstance(data.get("gaps"), list) else [])[:SESSION_GAPS]:
        if isinstance(g, dict) and _iso(g.get("from")) and _iso(g.get("to")):
            gaps.append({"from": g["from"], "to": g["to"], "seconds": _num(g.get("seconds"), 0, 10**7)})
    samples_in = data.get("samples") if isinstance(data.get("samples"), dict) else {}
    per_hop = samples_in.get("hops") if isinstance(samples_in.get("hops"), dict) else {}
    samples = {}
    for key, value in list(per_hop.items())[:SESSION_HOPS]:
        n = _int(int(key) if isinstance(key, str) and key.isdigit() else None, 1, 255)
        if n is None or not isinstance(value, dict):
            continue
        raw = []
        for pt in (value.get("raw") if isinstance(value.get("raw"), list) else [])[:SESSION_RAW]:
            if isinstance(pt, list) and len(pt) == 2 and _num(pt[0], 0, 10**6) is not None:
                raw.append([pt[0], None if pt[1] is None else _ms(pt[1])])
        buckets = []
        for b in (value.get("buckets") if isinstance(value.get("buckets"), list) else [])[:SESSION_BUCKETS]:
            if not isinstance(b, dict) or _num(b.get("t"), 0, 10**6) is None:
                continue
            sent, lost = _int(b.get("sent"), 0, 10**6), _int(b.get("lost"), 0, 10**6)
            if sent is None or lost is None or lost > sent:
                continue
            buckets.append({"t": b["t"], "sent": sent, "lost": lost, "min_ms": _ms(b.get("min_ms")),
                            "max_ms": _ms(b.get("max_ms")), "mean_ms": _ms(b.get("mean_ms"))})
        samples[str(n)] = {"raw": raw, "buckets": buckets}
    return {"target": _target(data.get("target")) or address, "address": address,
            "loss": geo.loss_verdict(hops),
            "started": _iso(data.get("started")), "ended": _iso(data.get("ended")),
            "interval_s": _num(data.get("interval_s"), 1, 60) or 1.0,
            "max_hops": _int(data.get("max_hops"), 1, 30) or 30,
            "duration_limit_s": _num(data.get("duration_limit_s"), 300, 8 * 3600) or 3600.0,
            "cycles": _int(data.get("cycles"), 0, 10**7) or 0,
            "stopped_by": data.get("stopped_by") if data.get("stopped_by") in STOPPED_BY else None,
            "reached_hop": _int(data.get("reached_hop"), 1, 255),
            "hops": hops, "changes": changes, "gaps": gaps,
            "resets": [r for r in (data.get("resets") if isinstance(data.get("resets"), list) else [])[:100]
                       if _iso(r)],
            "samples": {"resolution_s": _num(samples_in.get("resolution_s"), 1, 60) or 1.0,
                        "raw_seconds": _int(samples_in.get("raw_seconds"), 0, 10**6) or 1800,
                        "bucket_seconds": _int(samples_in.get("bucket_seconds"), 1, 3600) or 60,
                        "hops": samples}}


def reverse(data) -> dict | None:
    """A reverse trace (0.4.0) rebuilt from a file, or None when it is not one."""
    if not isinstance(data, dict):
        return None
    try:
        rebuilt = route(data.get("route"))
    except ImportRejected:
        return None
    probe_in = data.get("probe") if isinstance(data.get("probe"), dict) else {}
    country = probe_in.get("country")
    probe = {"id": _int(probe_in.get("id"), 1, 10**9), "asn": _int(probe_in.get("asn"), 1, 2**32 - 1),
             "country": country.upper() if isinstance(country, str) and re.fullmatch(r"[A-Za-z]{2}", country) else None,
             "distance_km": _num(probe_in.get("distance_km"), 0, 25_000),
             "lat": _num(probe_in.get("lat"), -90, 90), "lon": _num(probe_in.get("lon"), -180, 180)}
    if probe["lat"] is None or probe["lon"] is None:
        probe["lat"] = probe["lon"] = None
    return {"route": rebuilt, "measurement_id": _int(data.get("measurement_id"), 1, 10**12), "probe": probe,
            "af": data.get("af") if data.get("af") in (4, 6) else None,
            "trace_text": text(data.get("trace_text"), MAX_TRACE_TEXT, newlines=True) or ""}


def export(document) -> dict:
    """What the app shows from a route export: the rebuilt route, the target, the
    trace text and how it was made. The saved insight is not kept."""
    if not isinstance(document, dict) or "route" not in document:
        raise ImportRejected("that JSON file is not a route export")
    version = document.get("format_version")
    if isinstance(version, int) and not isinstance(version, bool) and version > FORMAT_VERSION:
        raise NewerFormat(version)
    rebuilt = route(document["route"])
    trace = document.get("trace") if isinstance(document.get("trace"), dict) else {}
    when = document.get("exported_at")
    return {
        "route": rebuilt,
        "target": _target(document.get("target")) or rebuilt.get("target"),
        "trace_text": text(trace.get("text"), MAX_TRACE_TEXT, newlines=True) or "",
        "argv": argv(trace.get("argv")),
        "source": trace.get("source") if trace.get("source") in SOURCES else "file",
        "origin_how": document.get("origin_how") if document.get("origin_how") in ORIGIN_HOWS else None,
        "exported_at": when if isinstance(when, str) and _WHEN.fullmatch(when[:40]) else None,
        "session": session(document.get("session")) if "session" in document else None,
        "reverse": reverse(document.get("reverse")) if "reverse" in document else None,
    }


def history_entry(entry) -> dict | None:
    """One history entry rebuilt, or None when it cannot be."""
    if not isinstance(entry, dict):
        return None
    try:
        rebuilt = route(entry.get("route"))
    except ImportRejected:
        return None
    when = entry.get("when")
    if isinstance(when, bool) or not isinstance(when, (int, float)) or not math.isfinite(when) or when < 0:
        return None
    count = lambda v: v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255 else None  # noqa: E731
    hops, placed = count(entry.get("hops")), count(entry.get("placed"))
    if hops is None or placed is None:
        return None
    return {"route": rebuilt, "target": _target(entry.get("target")) or rebuilt.get("target") or "",
            "when": float(when), "hops": hops, "placed": placed,
            "tool": text(entry.get("tool"), 200) or "", "argv": argv(entry.get("argv")),
            "trace_text": text(entry.get("trace_text"), MAX_TRACE_TEXT, newlines=True) or "",
            "source": entry.get("source") if entry.get("source") in SOURCES else "local",
            "origin_how": entry.get("origin_how") if entry.get("origin_how") in ORIGIN_HOWS else None,
            "session": session(entry.get("session")) if "session" in entry else None,
            "reverse": reverse(entry.get("reverse")) if "reverse" in entry else None}
