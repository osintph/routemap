"""
The routemap command line. Thin by rule: parse arguments, call the engine, print.

    routemap                                 open the window
    routemap TARGET                          open the window with the trace started
    routemap TARGET --json                   trace here, print the route model, exit
    routemap TARGET --png map.png --pdf r.pdf
    routemap TARGET --origin "Manila, PH"    or --origin 14.6,121.0
    routemap parse FILE [--json|--png|--pdf] analyse a trace run elsewhere
    routemap sites update [--dry-run]        refresh the carrier site-code table
    routemap cache clear                     forget cached Hoiho answers
    routemap --check-update                  ask GitHub for the latest release tag

Progress and the tool's own output go to stderr, so --json output on stdout can
be piped. Nothing is written anywhere except the files named on the command line
and, as in the window, the cache and history in the config folder.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import os
import sys

from routemap.__about__ import DISPLAY_NAME, NAME, __version__

SUBCOMMANDS = {"parse", "sites", "cache"}


def _err(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _headless_qt():
    """A QApplication for rendering PNG and PDF with no window and no display."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from routemap.gui.app import make_app
    return make_app()


def _origin(args, settings):
    from routemap import service

    if getattr(args, "origin", None):
        try:
            lat, lon, label = service.parse_origin_text(args.origin)
        except ValueError as exc:
            raise SystemExit(f"{NAME}: {exc}")
        return (lat, lon, label), "coords"
    if args.offline:
        chosen = settings.origin()
        return (chosen, settings.origin_mode) if chosen else (None, None)
    try:
        lat, lon, label, how = asyncio.run(service.resolve_origin(settings))
        return (lat, lon, label), how
    except Exception as exc:  # noqa: BLE001
        _err(f"{NAME}: could not find this machine's location ({exc}); "
             "routes start at the first located hop. Use --origin to set one.")
        return None, None


def _analyse(text, origin, settings, offline: bool):
    from routemap import service
    from routemap.engine import OFFLINE, analyse

    sources = OFFLINE if offline else service.sources_for(settings)

    def progress(source, state, detail):
        if state in ("timeout", "failed"):
            _err(f"{NAME}: {source} {state}{': ' + detail if detail else ''}")

    return asyncio.run(analyse(text, origin[:2] if origin else None, sources=sources,
                               progress=progress))


def _outputs(args, current: dict) -> int:
    from routemap import service

    if args.png or args.pdf:
        _headless_qt()
        from routemap.gui.app import write_export
        for fmt, path in (("png", args.png), ("pdf", args.pdf)):
            if path:
                write_export(fmt, path, current)
                _err(f"{NAME}: wrote {path}")
    if args.json or not (args.png or args.pdf):
        sys.stdout.write(service.export_json(
            current["route"], target=current["target"], trace_text=current["trace_text"],
            argv=current.get("argv"), source=current["source"],
            origin_how=current.get("origin_how")) if args.envelope else
            json.dumps(current["route"], indent=2, ensure_ascii=False) + "\n")
    return 0


# ------------------------------------------------------------------ commands ---

def cmd_trace(args) -> int:
    from routemap import config, service
    from routemap.engine import InvalidTarget, TraceParseError, validate_target
    from routemap.engine.runner import TraceToolMissing

    service.startup()
    settings = config.load_settings()
    if not (args.json or args.png or args.pdf):
        origin = None
        if args.origin:
            origin, _ = _origin(args, settings)
        from routemap.gui.app import run_gui
        return run_gui(args.target, origin_override=origin)
    try:
        target = validate_target(args.target)
    except InvalidTarget as exc:
        _err(f"{NAME}: {exc}")
        return 2
    origin, how = _origin(args, settings)
    try:
        result = service.run(target, settings, on_line=_err)
    except TraceToolMissing as exc:
        _err(f"{NAME}: {exc}")
        return 3
    if not result.text.strip():
        _err(f"{NAME}: {result.tool} printed nothing (exit code {result.returncode})")
        return 1
    try:
        route = _analyse(result.text, origin, settings, args.offline)
    except TraceParseError as exc:
        _err(f"{NAME}: {exc}")
        return 1
    body = route.to_dict()
    current = {"route": body, "target": target, "trace_text": result.text, "argv": result.argv,
               "source": "local", "origin_how": how if origin else "first-hop",
               "when": _dt.datetime.now().astimezone()}
    if settings.history_enabled:
        entry = config.history_entry(body, target=target, trace_text=result.text,
                                     argv=result.argv, source="local")
        entry["origin_how"] = current["origin_how"]
        config.add_history(entry, settings)
    return _outputs(args, current)


def cmd_parse(args) -> int:
    from routemap import config, service
    from routemap.engine import TraceParseError

    service.startup()
    settings = config.load_settings()
    try:
        with open(args.file, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError as exc:
        _err(f"{NAME}: {exc}")
        return 2
    origin, how = _origin(args, settings)
    try:
        route = _analyse(text, origin, settings, args.offline)
    except TraceParseError as exc:
        _err(f"{NAME}: {exc}")
        return 1
    current = {"route": route.to_dict(), "target": route.target or os.path.basename(args.file),
               "trace_text": text, "argv": None, "source": "file",
               "origin_how": how if origin else "first-hop",
               "when": _dt.datetime.now().astimezone()}
    return _outputs(args, current)


def cmd_sites(args) -> int:
    from routemap import config
    from routemap.engine import sitegen

    if args.action != "update":
        return 2
    out = config.site_codes_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    code = sitegen.main((["--dry-run"] if args.dry_run else []) + ["--out", str(out)])
    if code == 0 and not args.dry_run:
        _err(f"{NAME}: the updated table is used from now on instead of the bundled one. "
             f"Delete {out} to go back to the bundled table.")
    return code


def cmd_cache(args) -> int:
    from routemap import config
    from routemap.engine import SqliteCache

    if args.action != "clear":
        return 2
    path = config.cache_path()
    if not path.exists():
        print("The cache is already empty.")
        return 0
    print(f"Cleared {SqliteCache(path).clear()} cached hostnames from {path}.")
    return 0


def check_update() -> int:
    from routemap import service

    try:
        tag = asyncio.run(service.latest_release())
    except Exception as exc:  # noqa: BLE001
        _err(f"{NAME}: GitHub did not answer: {exc}")
        return 1
    print(f"installed: v{__version__}\nlatest:    {tag or 'no release yet'}")
    return 0


def smoke_test(out_dir: str) -> int:
    """Open the window offscreen, load the bundled sample, export all three formats.

    Contacts nothing: the sample is analysed with every network source off. Used
    by CI on each packaged binary, so it exercises the frozen app, not the source.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from importlib import resources

    from routemap.engine import OFFLINE, analyse_sync, schema
    from routemap.gui.app import make_app, write_export
    from routemap.gui.mainwindow import MainWindow

    app = make_app()
    text = resources.files("routemap.gui").joinpath("data/sample_trace.txt").read_text("utf-8")
    route = analyse_sync(text, (14.6, 121.0), sources=OFFLINE).to_dict()
    window = MainWindow()
    window.show()
    window.show_result(route, "heise.de", ["traceroute", "-m", "30", "heise.de"])
    app.processEvents()
    assert window.table.model().rowCount() == len(route["hops"]) > 0
    os.makedirs(out_dir, exist_ok=True)
    current = {"route": route, "target": "heise.de", "trace_text": text, "source": "file",
               "argv": None, "origin_how": "coords", "when": _dt.datetime.now().astimezone()}
    sizes = {}
    for fmt in ("png", "pdf", "json"):
        path = os.path.join(out_dir, f"smoke.{fmt}")
        write_export(fmt, path, current)
        sizes[fmt] = os.path.getsize(path)
    shot = os.path.join(out_dir, "smoke-window.png")
    window.grab().save(shot)
    with open(os.path.join(out_dir, "smoke.json"), encoding="utf-8") as handle:
        exported = json.load(handle)
    try:
        import jsonschema
        jsonschema.validate(exported["route"], schema())
        checked = "schema valid"
    except ImportError:
        checked = "schema not checked (jsonschema not bundled)"
    with open(os.path.join(out_dir, "smoke.pdf"), "rb") as handle:
        assert handle.read(5) == b"%PDF-"
    window.close()
    print(f"{NAME} {__version__} smoke test ok: {len(route['hops'])} hops, "
          f"{sum(1 for h in route['hops'] if h['lat'] is not None)} placed; "
          f"png {sizes['png']} B, pdf {sizes['pdf']} B, json {sizes['json']} B, {checked}")
    return 0


# ---------------------------------------------------------------------- main ---

def _common(parser):
    parser.add_argument("--json", action="store_true", help="print the route model as JSON")
    parser.add_argument("--envelope", action="store_true",
                        help="with --json: the full export (trace text, tool, flags) around the route")
    parser.add_argument("--png", metavar="FILE", help="write the map as a 1600x900 PNG")
    parser.add_argument("--pdf", metavar="FILE", help="write the PDF report")
    parser.add_argument("--origin", help='"lat,lon" or a city, e.g. "Manila, PH"')
    parser.add_argument("--offline", action="store_true",
                        help="contact nothing: site-code table and local hops only")


def _hide_console_for_gui():
    """Windows: the frozen binary is a console app so the CLI can print; when it
    was double-clicked (it owns its console alone), drop the console window."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        processes = (ctypes.c_uint * 4)()
        if kernel32.GetConsoleProcessList(processes, 4) <= 1:
            kernel32.FreeConsole()
    except Exception:  # noqa: BLE001
        pass


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # macOS passes -psn_... when launched from Finder on older systems.
    argv = [a for a in argv if not a.startswith("-psn_")]

    if argv and argv[0] in SUBCOMMANDS:
        parser = argparse.ArgumentParser(prog=NAME)
        sub = parser.add_subparsers(dest="command", required=True)
        p_parse = sub.add_parser("parse", help="analyse an existing trace")
        p_parse.add_argument("file")
        _common(p_parse)
        p_parse.set_defaults(func=cmd_parse)
        p_sites = sub.add_parser("sites", help="the carrier site-code table")
        p_sites.add_argument("action", choices=["update"])
        p_sites.add_argument("--dry-run", action="store_true")
        p_sites.set_defaults(func=cmd_sites)
        p_cache = sub.add_parser("cache", help="the Hoiho answer cache")
        p_cache.add_argument("action", choices=["clear"])
        p_cache.set_defaults(func=cmd_cache)
        args = parser.parse_args(argv)
        return args.func(args)

    parser = argparse.ArgumentParser(
        prog=NAME, description=f"{DISPLAY_NAME}: hostname-first, physics-checked traceroute "
                               "maps. With no arguments, opens the window.",
        epilog="Also: routemap parse FILE, routemap sites update, routemap cache clear.")
    parser.add_argument("target", nargs="?", help="hostname or IP address to trace")
    parser.add_argument("--version", action="version", version=f"{NAME} {__version__}")
    parser.add_argument("--check-update", action="store_true",
                        help="ask GitHub for the latest release tag, and nothing else")
    parser.add_argument("--smoke-test", metavar="DIR", help=argparse.SUPPRESS)
    _common(parser)
    args = parser.parse_args(argv)
    if args.smoke_test:
        return smoke_test(args.smoke_test)
    if args.check_update:
        return check_update()
    if args.target:
        return cmd_trace(args)
    if args.json or args.png or args.pdf:
        parser.error("give a target to trace, or use: routemap parse FILE")
    _hide_console_for_gui()
    from routemap import service
    from routemap.gui.app import run_gui
    service.startup()
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
