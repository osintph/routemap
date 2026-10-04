"""
Settings, history and the Hoiho cache: everything the app keeps, in one folder.

    macOS    ~/Library/Application Support/routemap/
    Windows  %APPDATA%\\routemap\\
    Linux    $XDG_CONFIG_HOME/routemap/  (default ~/.config/routemap/)

``ROUTEMAP_CONFIG_DIR`` overrides it (tests and portable installs use it).

What is in it, and nothing else:

    settings.json     the choices made in Settings, including the origin and the
                      RIPE Atlas key if one was entered
    cache.sqlite3     CAIDA Hoiho answers for router hostnames, 30 days by default
    ipgeo-cache.sqlite3  IP database answers for public hop addresses, same lifetime
    history.json      the last 50 traces, only while history is switched on
    site_codes.tsv    only after "routemap sites update"; replaces the bundled table

Qt-free, so the CLI uses exactly the same files as the window. Writes are
atomic (write to a temporary file, then rename) so a crash cannot leave a half
written settings file.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from routemap.__about__ import NAME
from routemap_engine.runner import DEFAULT_FLAGS

HISTORY_LIMIT = 50


def config_dir() -> Path:
    override = os.environ.get("ROUTEMAP_CONFIG_DIR")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / NAME
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / NAME
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / NAME


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ------------------------------------------------------------------ settings ---

ORIGIN_AUTO = "auto"       # public IP, looked up when needed
ORIGIN_CITY = "city"
ORIGIN_COORDS = "coords"
ORIGIN_MAP = "map"


@dataclass
class Settings:
    origin_mode: str = ORIGIN_AUTO
    origin_lat: float | None = None
    origin_lon: float | None = None
    origin_label: str | None = None
    tool: str = "auto"
    flags: dict = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_FLAGS.items()})
    timeout_seconds: int = 180
    use_hoiho: bool = True
    use_ip_db: bool = True
    use_ptr: bool = True
    cache_ttl_days: int = 30
    atlas_enabled: bool = False
    atlas_key: str = ""
    atlas_acknowledged: bool = False
    history_enabled: bool = True
    window_geometry: str = ""
    # 0.2.0
    # One switch for every online lookup the app makes beyond the trace itself:
    # Hoiho, the RIPEstat IP database tier and route details, the RIPE Atlas
    # baseline, and reverse DNS. Off: nothing new leaves the machine.
    online_lookups: bool = True
    projection: str = "flat"                 # "flat" or "globe"
    theme: str = "system"                    # "system", "light" or "dark": window, map, exports
    rtt_quiet_ms: float = 15.0               # RTT steps below this draw grey
    rtt_hot_ms: float = 60.0                 # and at or above this, fully warm
    sensitive_countries: list = field(default_factory=list)   # ISO codes, upper case
    falconeye_url: str = "https://falconeye.osintph.info"
    city_db_declined: bool = False           # "Not now" on the first-run download offer

    def origin(self) -> tuple[float, float, str] | None:
        """The chosen origin, or None when it is to come from the public IP."""
        if self.origin_mode == ORIGIN_AUTO or self.origin_lat is None or self.origin_lon is None:
            return None
        return (self.origin_lat, self.origin_lon,
                self.origin_label or f"{self.origin_lat}, {self.origin_lon}")

    def flags_for(self, tool: str) -> list[str]:
        chosen = self.flags.get(tool)
        return list(chosen) if isinstance(chosen, list) else list(DEFAULT_FLAGS[tool])


def settings_path() -> Path:
    return config_dir() / "settings.json"


def load_settings() -> Settings:
    """Settings from disk; defaults for anything missing or unreadable."""
    try:
        raw = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    known = {f.name for f in fields(Settings)}
    values = {k: v for k, v in raw.items() if k in known} if isinstance(raw, dict) else {}
    try:
        settings = Settings(**values)
    except TypeError:
        return Settings()
    merged = {k: list(v) for k, v in DEFAULT_FLAGS.items()}
    if isinstance(settings.flags, dict):
        merged.update({k: v for k, v in settings.flags.items()
                       if k in merged and isinstance(v, list) and all(isinstance(x, str) for x in v)})
    settings.flags = merged
    return normalise(settings)


def save_settings(settings: Settings) -> None:
    _atomic_write(settings_path(), json.dumps(asdict(settings), indent=2))
    try:
        # The Atlas key lives here; keep the file to its owner where the OS allows.
        os.chmod(settings_path(), 0o600)
    except OSError:
        pass


# ------------------------------------------------------------------- history ---

def history_path() -> Path:
    return config_dir() / "history.json"


def load_history() -> list[dict]:
    try:
        entries = json.loads(history_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in entries if isinstance(e, dict) and "route" in e] if isinstance(entries, list) else []


def add_history(entry: dict, settings: Settings) -> list[dict]:
    """Prepend *entry* (newest first, capped). A no-op while history is off."""
    if not settings.history_enabled:
        return []
    entries = [entry] + load_history()
    entries = entries[:HISTORY_LIMIT]
    _atomic_write(history_path(), json.dumps(entries, ensure_ascii=False))
    return entries


def clear_history() -> int:
    count = len(load_history())
    try:
        history_path().unlink()
    except FileNotFoundError:
        pass
    return count


def history_entry(route: dict, *, target: str, trace_text: str, argv: list[str] | None,
                  source: str) -> dict:
    hops = route.get("hops") or []
    return {
        "target": target,
        "when": time.time(),
        "source": source,               # "local" | "paste" | "file" | "atlas"
        "argv": list(argv or []),
        "hops": len(hops),
        "placed": sum(1 for h in hops if h.get("lat") is not None),
        "trace_text": trace_text,
        "route": route,
    }


# ------------------------------------------------------------- cache / sites ---

def cache_path() -> Path:
    return config_dir() / "cache.sqlite3"


def ip_cache_path() -> Path:
    """IP database answers (hop address -> location), kept as long as Hoiho's."""
    return config_dir() / "ipgeo-cache.sqlite3"


def ripe_cache_path() -> Path:
    """RIPEstat route details and the Atlas baseline, each with its own lifetime."""
    return config_dir() / "ripe-cache.sqlite3"


PROJECTIONS = ("flat", "globe")


def normalise(settings: Settings) -> Settings:
    """Clamp values a hand-edited file could break."""
    if settings.projection not in PROJECTIONS:
        settings.projection = "flat"
    if settings.theme not in ("system", "light", "dark"):
        settings.theme = "system"
    try:
        quiet = max(0.0, float(settings.rtt_quiet_ms))
        hot = max(quiet + 1.0, float(settings.rtt_hot_ms))
    except (TypeError, ValueError):
        quiet, hot = 15.0, 60.0
    settings.rtt_quiet_ms, settings.rtt_hot_ms = quiet, hot
    if not isinstance(settings.sensitive_countries, list):
        settings.sensitive_countries = []
    settings.sensitive_countries = sorted({str(c).strip().upper() for c in settings.sensitive_countries
                                           if len(str(c).strip()) == 2 and str(c).strip().isalpha()})
    url = str(settings.falconeye_url or "").strip().rstrip("/")
    settings.falconeye_url = url if url.startswith(("https://", "http://")) else \
        "https://falconeye.osintph.info"
    return settings


def site_codes_path() -> Path:
    return config_dir() / "site_codes.tsv"
