"""
The routemap command line.

Thin by rule: parse arguments, call the engine, print. Everything that decides
where a hop is lives in routemap.engine.

At this stage only the engine-facing commands exist:

    routemap parse FILE [--origin "14.6,121.0"] [--offline]   route model as JSON
    routemap --version

The window, live tracing, exports and the rest arrive with the desktop app.
"""
from __future__ import annotations

import argparse
import json
import sys

from routemap.__about__ import DISPLAY_NAME, NAME, __version__


def _origin(text: str | None):
    if not text:
        return None
    from routemap.engine import normalise_origin

    parts = [p.strip() for p in text.split(",")]
    if len(parts) == 2:
        try:
            origin = normalise_origin(float(parts[0]), float(parts[1]))
        except ValueError:
            origin = None
        if origin is not None:
            return origin
    from routemap.engine import cities

    city = cities.lookup(text)
    if city is None:
        raise SystemExit(f"{NAME}: no city or lat,lon matches {text!r}")
    return (city["lat"], city["lon"])


def _cmd_parse(args) -> int:
    from routemap.engine import OFFLINE, TraceParseError, analyse_sync

    try:
        with open(args.file, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError as exc:
        print(f"{NAME}: {exc}", file=sys.stderr)
        return 2
    try:
        route = analyse_sync(text, _origin(args.origin),
                             sources=OFFLINE if args.offline else None)
    except TraceParseError as exc:
        print(f"{NAME}: {exc}", file=sys.stderr)
        return 1
    json.dump(route.to_dict(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=NAME, description=f"{DISPLAY_NAME}: "
                                     "hostname-first, physics-checked traceroute maps.")
    parser.add_argument("--version", action="version", version=f"{NAME} {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_parse = sub.add_parser("parse", help="analyse an existing trace and print the route as JSON")
    p_parse.add_argument("file")
    p_parse.add_argument("--origin", help='"lat,lon" or a city name, e.g. "Manila"')
    p_parse.add_argument("--offline", action="store_true",
                         help="contact nothing: site-code table and local hops only")
    p_parse.set_defaults(func=_cmd_parse)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
