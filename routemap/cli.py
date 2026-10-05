"""
The routemap command line. Thin by rule: parse arguments, call the engine, print.

    routemap                                 open the window
    routemap TARGET                          open the window with the trace started
    routemap TARGET --json                   trace here, print the route model, exit
    routemap TARGET --png map.png --pdf r.pdf
    routemap TARGET --origin "Manila, PH"    or --origin 14.6,121.0
    routemap parse FILE [--json|--png|--pdf] analyse a trace run elsewhere
    routemap sites update [--dry-run]        refresh the carrier site-code table
    routemap cache clear                     forget cached Hoiho and IP database answers
    routemap data update                     download this month's DB-IP Lite City and ASN
    routemap data import FILE                install a DB-IP Lite City file (offline machines)
    routemap data status                     which offline databases are installed
    routemap TARGET --pdf r.pdf --compare earlier.json   include a comparison
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
import re
import sys

from routemap.__about__ import DISPLAY_NAME, NAME, VERSION

SUBCOMMANDS = {"parse", "sites", "cache", "data"}


def _err(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _headless_qt():
    """A QApplication for rendering PNG and PDF with no window shown."""
    from routemap import config
    from routemap.gui import theme
    from routemap.gui.app import headless_platform, make_app
    headless_platform()
    app = make_app()
    theme.apply(app, config.load_settings().theme)
    return app


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
    from routemap_engine import OFFLINE, analyse

    sources = service.offline_sources() if offline else service.sources_for(settings)

    def progress(source, state, detail):
        if state in ("timeout", "failed"):
            _err(f"{NAME}: {source} {state}{': ' + detail if detail else ''}")

    return asyncio.run(analyse(text, origin[:2] if origin else None, sources=sources,
                               progress=progress))


def _insight(args, current: dict, settings) -> None:
    """The AS path and countries (offline, always); RIPE details unless --offline
    or Online lookups are off; and a comparison when --compare names an export."""
    from routemap import insight, service

    route = current["route"]
    ins = insight.offline(route, settings)
    if args.offline or not insight.online_allowed(settings):
        ins["online"] = {"status": insight.OFF}
    else:
        asyncio.run(insight.online(route, ins, settings, user_agent=service.user_agent(),
                                   sourceapp=service.SOURCEAPP))
    current["insight"] = ins
    if getattr(args, "compare", None):
        from routemap import imported
        from routemap_engine import diff as route_diff
        # The same door as the window's Compare: capped, rebuilt from the route format.
        try:
            document = imported.export(imported.parse_json(imported.read_file(args.compare)))
            old = document["route"]
        except (ValueError, KeyError, TypeError) as exc:
            raise SystemExit(f"{NAME}: {args.compare} is not a route export ({exc})")
        result = route_diff.diff_routes(old, route)
        current["comparison"] = {"label": (document["exported_at"] or args.compare)[:16].replace("T", " "),
                                 "summary": result["summary"], "changes": result["changes"],
                                 "old_route": old, "new_marks": result["new_marks"],
                                 "old_marks": result["old_marks"]}
        _err(f"{NAME}: compared with {args.compare}: {result['summary']}")


def _outputs(args, current: dict) -> int:
    from routemap import config, service

    settings = config.load_settings()
    _insight(args, current, settings)

    if args.png or args.pdf:
        _headless_qt()
        from routemap.gui.app import write_export
        for fmt, path in (("png", args.png), ("pdf", args.pdf)):
            if path:
                write_export(fmt, path, current, settings=settings)
                _err(f"{NAME}: wrote {path}")
    if args.json or not (args.png or args.pdf):
        sys.stdout.write(service.export_json(
            current["route"], target=current["target"], trace_text=current["trace_text"],
            argv=current.get("argv"), source=current["source"],
            origin_how=current.get("origin_how"), insight=current.get("insight"),
            comparison=current.get("comparison")) if args.envelope else
            json.dumps(current["route"], indent=2, ensure_ascii=False) + "\n")
    return 0


# ------------------------------------------------------------------ commands ---

def cmd_trace(args) -> int:
    from routemap import config, service
    from routemap_engine import InvalidTarget, TraceParseError, validate_target
    from routemap_engine.runner import TraceToolMissing

    service.startup()
    settings = config.load_settings()
    if not (args.json or args.png or args.pdf):
        return open_window([args.target] + (["--origin", args.origin] if args.origin else []))
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
    from routemap_engine import TraceParseError

    service.startup()
    settings = config.load_settings()
    from routemap import imported
    try:
        text = imported.read_file(args.file)
    except imported.ImportRejected as exc:
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


SITE_CODE = re.compile(r"[a-z0-9-]{2,12}")


def _bad_site_rows(text: str) -> list[str]:
    """Lines of a site-code table that are not carrier, code, city, country,
    latitude, longitude, source; the code must match SITE_CODE."""
    bad = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split("\t")
        ok = len(f) == 7 and SITE_CODE.fullmatch(f[1]) and re.fullmatch(r"[a-z0-9-]{1,32}", f[0]) \
            and re.fullmatch(r"[A-Z]{2}", f[3]) and all(ch.isprintable() and ch not in "<>" for ch in f[2])
        try:
            ok = ok and -90 <= float(f[4]) <= 90 and -180 <= float(f[5]) <= 180
        except ValueError:
            ok = False
        if not ok:
            bad.append(line[:80])
    return bad


def cmd_sites(args) -> int:
    from routemap import config
    from routemap_engine import sitegen

    if args.action != "update":
        return 2
    out = config.site_codes_path()
    config.private_dir(out.parent)
    if args.dry_run:
        return sitegen.main(["--dry-run", "--out", str(out)])
    # Built beside the table in use, checked, then moved over it: a looking-glass
    # page that returns nonsense replaces nothing (hardening 17).
    staging = config.private_file(out.with_name(out.name + ".new"))
    try:
        code = sitegen.main(["--out", str(staging)])
        if code == 0:
            bad = _bad_site_rows(staging.read_text(encoding="utf-8"))
            if bad:
                _err(f"{NAME}: the new table has {len(bad)} line(s) that are not site codes, "
                     f"for example {bad[0]!r}; the table in use is unchanged.")
                return 1
            os.replace(staging, out)
    finally:
        staging.unlink(missing_ok=True)
    if code == 0 and not args.dry_run:
        _err(f"{NAME}: the updated table is used from now on instead of the bundled one. "
             f"Delete {out} to go back to the bundled table.")
    return code


def cmd_cache(args) -> int:
    from routemap import config
    from routemap_engine import SqliteCache

    if args.action != "clear":
        return 2
    cleared = 0
    for path in (config.cache_path(), config.ip_cache_path(), config.ripe_cache_path()):
        if path.exists():
            cleared += SqliteCache(path).clear()
    print(f"Cleared {cleared} cached answers (Hoiho hostnames, IP database addresses, RIPE details)."
          if cleared else "The cache is already empty.")
    return 0


def check_update() -> int:
    from routemap import service

    try:
        latest = asyncio.run(service.latest_release())
    except Exception as exc:  # noqa: BLE001
        _err(f"{NAME}: GitHub did not answer: {exc}")
        return 1
    print(f"installed: v{VERSION}\nlatest:    {latest['tag'] if latest else 'no release yet'}")
    if latest and service.release_order(latest["tag"]) > service.release_order(f"v{VERSION}"):
        offer = service.installer_for(latest["assets"])
        print(f"download:  {offer[1] if offer else latest['page']}")
    return 0


def cmd_data(args) -> int:
    """The DB-IP Lite databases: status, update (download), import (a file)."""
    from routemap import dbip, service

    if args.action == "status":
        for kind, db in (("city", dbip.city_database()), ("asn", dbip.asn_database())):
            if db is None:
                print(f"{kind}: not installed")
            else:
                note = " (bundled)" if db.bundled else ""
                stale = "; a newer month is out: routemap data update" if dbip.is_stale(db) else ""
                print(f"{kind}: {db.month}{note}, {db.path}{stale}")
        print(f"{dbip.ATTRIBUTION} ({dbip.ATTRIBUTION_URL}), {dbip.LICENCE}")
        return 0
    if args.action == "import":
        if not args.file:
            _err(f"{NAME}: routemap data import FILE")
            return 2
        try:
            db = dbip.import_file(args.file, "city")
        except dbip.DatabaseError as exc:
            _err(f"{NAME}: {exc}")
            return 1
        print(f"installed {db.label}: {db.path}")
        return 0
    last = [-1]

    def progress(done, total):
        if total:
            pct = int(100 * done / total)
            if pct // 10 != last[0]:
                last[0] = pct // 10
                _err(f"{NAME}: {done / 1e6:.0f} of {total / 1e6:.0f} MB")

    for kind in ("city", "asn"):
        _err(f"{NAME}: downloading DB-IP Lite {kind} from download.db-ip.com")
        last[0] = -1
        try:
            db = dbip.download(kind, user_agent=service.user_agent(), progress=progress)
        except dbip.DatabaseError as exc:
            _err(f"{NAME}: {exc}")
            return 1
        print(f"installed {db.label}: {db.path}")
    return 0


def smoke_test(out_dir: str) -> int:
    """Open the window offscreen, load the bundled sample, export all three formats.

    Contacts nothing: the sample is analysed with every network source off. Used
    by CI on each packaged binary, so it exercises the frozen app, not the source.
    """
    from importlib import resources

    from routemap_engine import OFFLINE, analyse_sync, schema
    from routemap.gui.app import headless_platform, make_app, write_export
    from routemap.gui.mainwindow import MainWindow

    headless_platform()
    app = make_app()
    from routemap.gui import theme
    theme.apply(app, "light")          # the same look on every platform's smoke test
    text = resources.files("routemap.gui").joinpath("data/sample_trace.txt").read_text("utf-8")
    route = analyse_sync(text, (14.6, 121.0), sources=OFFLINE).to_dict()
    window = MainWindow()
    window.show()
    window.show_result(route, "heise.de", ["traceroute", "-m", "30", "heise.de"])
    app.processEvents()
    assert window.table.model().rowCount() == len(route["hops"]) > 0
    os.makedirs(out_dir, exist_ok=True)
    from routemap import config, insight
    settings = config.Settings(online_lookups=False)
    ins = insight.offline(route, settings)
    ins["online"] = {"status": insight.OFF}
    # The bundled DB-IP Lite ASN file unpacked and answered: the AS path works offline.
    assert ins["as_path"], "no AS path: the bundled ASN database did not load"
    window.insight.show_summary(route, ins)
    window.map.set_route(route, "heise.de", keep_view=True)
    app.processEvents()
    from routemap.gui import parity
    # newline="\n": the same bytes on every platform (Windows text mode wrote
    # \r\n and the cross-platform comparison saw every line differ).
    with open(os.path.join(out_dir, "parity.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(parity.snapshot(window), handle, indent=1, sort_keys=True)
    window.map.set_projection("globe")
    app.processEvents()
    globe = os.path.join(out_dir, "smoke-globe.png")
    window.grab().save(globe)
    window.map.set_projection("flat")
    current = {"route": route, "target": "heise.de", "trace_text": text, "source": "file",
               "argv": None, "origin_how": "coords", "when": _dt.datetime.now().astimezone(),
               "insight": ins}
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
        pdf = handle.read()
    assert pdf[:5] == b"%PDF-"
    # A platform with no fonts writes a PDF with no font objects and no text.
    assert b"/Font" in pdf, "the PDF has no fonts: text did not render on this platform"
    window.close()
    from routemap.__about__ import build_commit
    summary = (f"{NAME} {VERSION} commit {build_commit()} smoke test ok: {len(route['hops'])} hops, "
               f"{sum(1 for h in route['hops'] if h['lat'] is not None)} placed; "
               f"AS path {ins['as_path_text']}; "
               f"png {sizes['png']} B, pdf {sizes['pdf']} B, json {sizes['json']} B, {checked}")
    with open(os.path.join(out_dir, "result.txt"), "w", encoding="utf-8") as handle:
        handle.write(summary + "\n")
    print(summary)
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
                        help="contact nothing: offline data only (site codes, DB-IP Lite)")
    parser.add_argument("--compare", metavar="FILE",
                        help="compare with an earlier JSON export (in the PDF and --envelope JSON)")


def _frozen_windows() -> bool:
    return sys.platform == "win32" and (getattr(sys, "frozen", False) or "__compiled__" in globals())


def open_window(args: list[str]) -> int:
    """Open the window. From the Windows console binary (routemap-cli.exe), start
    the windowed routemap.exe beside it, fully detached, so the window never
    belongs to this console and survives it being closed."""
    if _frozen_windows():
        import subprocess
        gui = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "routemap.exe")
        if not os.path.exists(gui):
            _err(f"{NAME}: routemap.exe is not next to this program; open it directly.")
            return 2
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([gui, *args], creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return 0
    from routemap import service
    from routemap.gui.main import main as gui_main
    service.startup()
    return gui_main(args)


def utf8_streams(platform: str = sys.platform) -> None:
    """On Windows, write redirected output as UTF-8.

    A console gets Unicode through the console API whatever this says, but
    output redirected to a file or a pipe is encoded in the ANSI code page
    (cp1252 and the like), so a "\u00b7" or a city name like "Z\u00fcrich" reaches
    the next program as bytes it reads as "\ufffd". UTF-8 is what scripts, CI
    logs and JSON readers expect.
    """
    if not platform.startswith("win"):
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _print_and_exit(text: str) -> type[argparse.Action]:
    class _Print(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            print(text)
            parser.exit()
    return _Print


def main(argv: list[str] | None = None) -> int:
    utf8_streams()
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
        p_data = sub.add_parser("data", help="the DB-IP Lite offline databases")
        p_data.add_argument("action", choices=["update", "import", "status"])
        p_data.add_argument("file", nargs="?", help="with import: a .mmdb or .mmdb.gz file")
        p_data.set_defaults(func=cmd_data)
        args = parser.parse_args(argv)
        return args.func(args)

    parser = argparse.ArgumentParser(
        prog=NAME, description=f"{DISPLAY_NAME}: hostname-first, physics-checked traceroute "
                               "maps. With no arguments, opens the window.",
        epilog="Also: routemap parse FILE, routemap sites update, routemap cache clear, "
               "routemap data update|import|status.")
    parser.add_argument("target", nargs="?", help="hostname or IP address to trace")
    from routemap.__about__ import engine_line, version_line
    # Two lines (the app, then the engine); argparse's own version action folds newlines.
    parser.add_argument("--version", nargs=0, action=_print_and_exit(f"{NAME} {version_line()}\n{engine_line()}"),
                        help="show the app's and the engine's version and commit, and exit")
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
    return open_window([])


if __name__ == "__main__":
    sys.exit(main())
