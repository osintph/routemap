"""
Entry point of the windowed executable (routemap.exe on Windows, the .app on
macOS). It never prints and never needs a console: on Windows it is built for
the Windows GUI subsystem, so Explorer gives it no console window and closing a
terminal it was started from does not take it down.

    routemap [TARGET] [--origin "Manila, PH"]      open the window (and trace)

Everything else on the command line belongs to routemap-cli. Two hidden flags
exist for CI: --smoke-test DIR (exports, then exits) and --smoke-hold SECONDS DIR
(keeps the window open, writes a heartbeat, records whether a console is
attached, then exits) so a runner can prove the process outlives its launcher.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time


def _console_window() -> int:
    if sys.platform != "win32":
        return 0
    try:
        import ctypes
        return int(ctypes.windll.kernel32.GetConsoleWindow() or 0)
    except Exception:  # noqa: BLE001
        return -1


def smoke_hold(seconds: float, out_dir: str) -> int:
    from PySide6.QtCore import QTimer

    from routemap.gui.app import make_app
    from routemap.gui.mainwindow import MainWindow

    os.makedirs(out_dir, exist_ok=True)
    app = make_app()
    window = MainWindow()
    window.show()
    with open(os.path.join(out_dir, "hold.json"), "w", encoding="utf-8") as handle:
        json.dump({"pid": os.getpid(), "ppid": os.getppid(), "console_window": _console_window(),
                   "platform": app.platformName(), "started": time.time()}, handle)
    beats = {"n": 0}

    def beat():
        beats["n"] += 1
        with open(os.path.join(out_dir, "heartbeat"), "w", encoding="utf-8") as handle:
            handle.write(str(beats["n"]))

    timer = QTimer()
    timer.timeout.connect(beat)
    timer.start(1000)

    def done():
        with open(os.path.join(out_dir, "done"), "w", encoding="utf-8") as handle:
            handle.write(str(beats["n"]))
        app.quit()

    QTimer.singleShot(int(seconds * 1000), done)
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    argv = [a for a in argv if not a.startswith("-psn_")]
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("target", nargs="?")
    parser.add_argument("--origin")
    parser.add_argument("--smoke-test", metavar="DIR")
    parser.add_argument("--smoke-hold", nargs=2, metavar=("SECONDS", "DIR"))
    args, _unknown = parser.parse_known_args(argv)

    if args.smoke_test:
        from routemap.cli import smoke_test
        return smoke_test(args.smoke_test)
    if args.smoke_hold:
        return smoke_hold(float(args.smoke_hold[0]), args.smoke_hold[1])

    from routemap import config, service
    from routemap.gui.app import run_gui

    service.startup()
    origin = None
    if args.origin:
        try:
            origin = service.parse_origin_text(args.origin)
        except ValueError:
            origin = None
    _ = config
    return run_gui(args.target if args.target and not args.target.startswith("-") else None,
                   origin_override=origin)


if __name__ == "__main__":
    sys.exit(main())
