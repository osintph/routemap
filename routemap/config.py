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
import re
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
    return _default_config_dir()


def _default_config_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / NAME
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / NAME
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / NAME


# The files the app keeps in its folder; each is 0600 and the folder 0700
# (RM-11): they name where the user traces to and through.
OWN_FILES = ("settings.json", "history.json", "cache.sqlite3", "ipgeo-cache.sqlite3",
             "ripe-cache.sqlite3", "site_codes.tsv")
SQLITE_COMPANIONS = ("", "-wal", "-shm", "-journal")


def private_dir(path: Path) -> Path:
    """Create *path* as 0700. An existing folder is tightened when it is the
    app's own (the default config folder or one inside it), never a folder a
    ROUTEMAP_CONFIG_DIR override points at, which may hold anything."""
    path = Path(path)
    if not path.exists():
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    elif os.name != "nt":
        own = _default_config_dir()
        if path == own or own in path.parents:
            os.chmod(path, 0o700)
    return path


def private_file(path: Path) -> Path:
    """*path* as 0600, created empty when missing (SQLite gives its journal
    files the database's own mode, so a cache made this way stays private)."""
    path = Path(path)
    private_dir(path.parent)
    if os.name == "nt":
        path.touch(exist_ok=True)
        return path
    os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
    for suffix in SQLITE_COMPANIONS:
        try:
            os.chmod(str(path) + suffix, 0o600)
        except FileNotFoundError:
            pass
    return path


def tighten() -> None:
    """At start: the folder an older version made 0755, and its files 0644."""
    if os.name == "nt":
        return
    root = config_dir()
    if not root.is_dir():
        return
    private_dir(root)
    for name in OWN_FILES:
        for suffix in SQLITE_COMPANIONS:
            if (root / (name + suffix)).is_file():
                os.chmod(root / (name + suffix), 0o600)
    data = root / "data"
    if data.is_dir() and not data.is_symlink():
        private_dir(data)
        for item in data.iterdir():
            if item.is_file() and not item.is_symlink() and ".mmdb" in item.name:
                os.chmod(item, 0o600)


def _atomic_write(path: Path, text: str) -> None:
    private_dir(path.parent)
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
    # 0.2.0-beta.6
    tour_seen: bool = False                  # the first-run tour was finished or skipped
    rtt_palette: str = "standard"            # "standard" or "colour-blind" (gui/theme.py)
    # 0.3.0-beta.1: continuous mode (limits enforced by routemap_engine.watch)
    live_interval: float = 1.0               # seconds per cycle, 1 to 60
    live_duration_min: int = 60              # minutes before a session stops itself, 5 to 480
    live_keep_history: bool = True           # keep stopped sessions in History
    # 0.4.0-beta.1 "Paths"
    ip_version: str = "auto"                 # "auto" (the system's order), "4" or "6"
    paths_budget: int = 1500                 # probes per path discovery, 100 to 1,500 (engine cap)
    # When the user agreed that reverse traces publish their public IP (ISO
    # time, UTC); "" means no consent, and no reverse trace runs.
    reverse_consent_at: str = ""

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
    except (OSError, ValueError, RecursionError):
        return Settings()
    known = {f.name for f in fields(Settings)}
    values = {k: v for k, v in raw.items() if k in known} if isinstance(raw, dict) else {}
    # Settings saved before the tour existed belong to someone who has used the
    # app already: the tour is for a first run, and Help > Show the Tour has it.
    values.setdefault("tour_seen", True)
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
        from routemap import imported
        entries = imported.parse_json(history_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(entries, list):
        return []
    # Rebuilt like an export: the file may have been written by anything (hardening 3).
    from routemap import imported
    rebuilt = (imported.history_entry(e) for e in entries[:HISTORY_LIMIT])
    return [e for e in rebuilt if e is not None]


# Stored continuous sessions, all together: past this the oldest are dropped
# first (Settings > Live says so). Traces are capped by HISTORY_LIMIT only.
SESSIONS_MAX_BYTES = 50_000_000


def _size(entry: dict) -> int:
    return len(json.dumps(entry.get("session"), ensure_ascii=False).encode("utf-8")) if entry.get("session") else 0


def cap_sessions(entries: list[dict], limit: int = SESSIONS_MAX_BYTES) -> list[dict]:
    """*entries* (newest first) with the oldest sessions dropped until the
    sessions together fit in *limit* bytes. Traces are kept."""
    total = sum(_size(e) for e in entries)
    out = list(entries)
    for e in reversed(entries):
        if total <= limit:
            break
        if e.get("session"):
            out.remove(e)
            total -= _size(e)
    return out


def add_history(entry: dict, settings: Settings) -> list[dict]:
    """Prepend *entry* (newest first, capped). A no-op while history is off."""
    if not settings.history_enabled:
        return []
    entries = [entry] + load_history()
    entries = cap_sessions(entries[:HISTORY_LIMIT])
    _atomic_write(history_path(), json.dumps(entries, ensure_ascii=False))
    return entries


def attach_to_history(when: float, key: str, value: dict) -> bool:
    """Store *value* under *key* in the history entry made at *when* (a reverse
    trace joins the trace it reverses). False when that entry is gone."""
    entries = load_history()
    for entry in entries:
        if isinstance(entry, dict) and entry.get("when") == when:
            entry[key] = value
            _atomic_write(history_path(), json.dumps(entries, ensure_ascii=False))
            return True
    return False


def clear_history() -> int:
    count = len(load_history())
    try:
        history_path().unlink()
    except FileNotFoundError:
        pass
    return count


def history_entry(route: dict, *, target: str, trace_text: str, argv: list[str] | None,
                  source: str, session: dict | None = None) -> dict:
    hops = route.get("hops") or []
    entry = {
        "target": target,
        "when": time.time(),
        "source": source,               # "local" | "paste" | "file" | "atlas"
        "argv": list(argv or []),
        "hops": len(hops),
        "placed": sum(1 for h in hops if h.get("lat") is not None),
        "trace_text": trace_text,
        "route": route,
    }
    if session is not None:
        entry["session"] = session
    return entry


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
IP_VERSIONS = ("auto", "4", "6")
CONSENT_WHEN = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")


def normalise(settings: Settings) -> Settings:
    """Clamp values a hand-edited file could break."""
    if settings.projection not in PROJECTIONS:
        settings.projection = "flat"
    if settings.theme not in ("system", "light", "dark"):
        settings.theme = "system"
    if settings.rtt_palette not in ("standard", "colour-blind"):
        settings.rtt_palette = "standard"
    try:
        settings.live_interval = min(60.0, max(1.0, float(settings.live_interval)))
    except (TypeError, ValueError):
        settings.live_interval = 1.0
    if settings.live_interval != settings.live_interval:      # NaN
        settings.live_interval = 1.0
    try:
        settings.live_duration_min = int(min(480, max(5, int(settings.live_duration_min))))
    except (TypeError, ValueError, OverflowError):
        settings.live_duration_min = 60
    settings.live_keep_history = bool(settings.live_keep_history)
    if settings.ip_version not in IP_VERSIONS:
        settings.ip_version = "auto"
    try:
        settings.paths_budget = int(min(1500, max(100, int(settings.paths_budget))))
    except (TypeError, ValueError, OverflowError):
        settings.paths_budget = 1500
    consent = settings.reverse_consent_at
    settings.reverse_consent_at = consent if isinstance(consent, str) and CONSENT_WHEN.fullmatch(consent) else ""
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
