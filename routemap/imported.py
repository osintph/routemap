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

MAX_FILE_BYTES = 1_000_000
MAX_TEXT = 300
MAX_ITEMS = 512
MAX_TRACE_TEXT = 256_000
SOURCES = ("local", "paste", "file", "atlas")
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
        raise ImportRejected(f"the file is {size // 1000} KB; a route export is far smaller "
                             f"(at most {MAX_FILE_BYTES // 1000} KB)")
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
        for i, v in enumerate(value[:MAX_ITEMS]):
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
    rebuilt["parser_label"] = PARSER_LABELS.get(rebuilt.get("parser"), "")
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


def export(document) -> dict:
    """What the app shows from a route export: the rebuilt route, the target, the
    trace text and how it was made. The saved insight is not kept."""
    if not isinstance(document, dict) or "route" not in document:
        raise ImportRejected("that JSON file is not a route export")
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
            "origin_how": entry.get("origin_how") if entry.get("origin_how") in ORIGIN_HOWS else None}
