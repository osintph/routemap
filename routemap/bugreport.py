"""
Help > Create Bug Report: a zip the user saves and sends themselves.

Qt-free. :func:`contents` returns the exact files and bytes the zip will hold,
so the dialog shows the user precisely what :func:`write_zip` writes. Nothing
here sends anything anywhere.

WHAT IS LEFT OUT
----------------
* Every setting whose name says key, token, secret, password, passphrase,
  credential or auth, at any depth, and any value anywhere that has the shape
  of an API key (a UUID, as RIPE Atlas keys are): replaced by "(removed)".
* A set origin (city, coordinates, label), unless the user includes the last
  trace, which carries the origin anyway; the dialog says so.
* A FalconEye address other than the public default, which can name a private
  server.
* The last trace, unless the user ticks it: it names the target, every hop
  address and the origin.
"""
from __future__ import annotations

import dataclasses
import io
import json
import platform
import re
import sys
import zipfile

from routemap import config
from routemap.__about__ import DISPLAY_NAME, engine_line, version_line

REMOVED = "(removed)"
SECRET_NAME = re.compile(r"key|token|secret|passw|passphrase|credential|auth", re.I)
SECRET_VALUE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
ORIGIN_FIELDS = ("origin_lat", "origin_lon", "origin_label")
DEFAULT_FALCONEYE = config.Settings().falconeye_url

ABOUT = "about.txt"
SETTINGS = "settings.json"
TRACE = "last-trace.json"


def _scrub(value, name: str = ""):
    if name and SECRET_NAME.search(name):
        return REMOVED if value not in (None, "", [], {}) else value
    if isinstance(value, dict):
        return {k: _scrub(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, str) and SECRET_VALUE.search(value):
        return SECRET_VALUE.sub(REMOVED, value)
    return value


def settings_view(settings: config.Settings, include_origin: bool) -> dict:
    data = _scrub(dataclasses.asdict(settings))
    if not include_origin:
        for name in ORIGIN_FIELDS:
            if data.get(name) not in (None, ""):
                data[name] = REMOVED
    if data.get("falconeye_url") and data["falconeye_url"] != DEFAULT_FALCONEYE:
        data["falconeye_url"] = REMOVED
    return data


def about_text() -> str:
    try:
        from PySide6 import __version__ as pyside
    except Exception:  # noqa: BLE001
        pyside = "not installed"
    frozen = "compiled build" if getattr(sys, "frozen", False) or "__compiled__" in globals() else "from source"
    import os
    kind = "AppImage" if os.environ.get("APPIMAGE") else frozen
    return "\n".join([
        version_line(),
        engine_line(),
        f"OS       {platform.system()} {platform.release()} ({platform.machine()})",
        f"Detail   {platform.platform()}",
        f"Python   {platform.python_version()}",
        f"Qt       PySide6 {pyside}",
        f"Build    {kind}",
        "",
    ])


def trace_view(current: dict) -> dict:
    return {"target": current.get("target"), "trace_text": current.get("trace_text", ""),
            "argv": current.get("argv"), "route": current.get("route")}


def contents(settings: config.Settings, current: dict | None, include_trace: bool) -> list[tuple[str, bytes]]:
    """The files of the report, in order, as (name, bytes)."""
    files = [(ABOUT, about_text().encode("utf-8")),
             (SETTINGS, (json.dumps(settings_view(settings, include_origin=include_trace and bool(current)),
                                    indent=2, ensure_ascii=False) + "\n").encode("utf-8"))]
    if include_trace and current:
        files.append((TRACE, (json.dumps(_scrub(trace_view(current)), indent=2, ensure_ascii=False)
                              + "\n").encode("utf-8")))
    return files


def write_zip(path, files: list[tuple[str, bytes]]) -> None:
    """Write exactly *files* to *path*; nothing else goes in."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data)
    with open(path, "wb") as out:
        out.write(buf.getvalue())


def suggested_name(when) -> str:
    return f"{DISPLAY_NAME.replace(' ', '')}-bug-report-{when:%Y%m%d-%H%M}.zip"
