"""
The DB-IP Lite databases: where they live, how they arrive, which one is in use.

Two files, both CC BY 4.0 ("IP Geolocation by DB-IP", https://db-ip.com):

  ASN Lite   about 9 MB. Shipped inside the app (gzipped, routemap/data/), so
             the AS path works offline from the first trace. Unpacked once into
             the data folder; a newer month downloaded by "Update now" wins.
  City Lite  about 127 MB unpacked, 60 MB to download. Not shipped: fetched on
             first run if the user agrees, or imported from a file on a machine
             with no internet. Until it is there, IP database placements come
             from the online tier (RIPEstat) and the Source column says so.

Files are named by month (dbip-city-lite-2026-10.mmdb) in config_dir()/data.
Every file is opened and its database type checked before it replaces the old
one, so a truncated download or the wrong file never becomes the live copy.

Qt-free: the window and the CLI both use it. Network calls only happen in
download(), which the user starts.
"""
from __future__ import annotations

import datetime as _dt
import gzip
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Callable

from routemap import config

KINDS = {"city": "DBIP-City-Lite", "asn": "DBIP-ASN-Lite"}
URL = "https://download.db-ip.com/free/dbip-{kind}-lite-{month}.mmdb.gz"
ATTRIBUTION = "IP Geolocation by DB-IP"
ATTRIBUTION_URL = "https://db-ip.com"
LICENCE = "CC BY 4.0"
BUNDLED_ASN = "data/dbip-asn-lite.mmdb.gz"
DOWNLOAD_TIMEOUT = 60.0
# Ceilings well above the real files (City Lite is about 60 MB packed and
# 125 MB unpacked), so a misbehaving server or a gzip bomb cannot fill the
# disk (RM-12). A redirect is followed only to https on db-ip.com.
MAX_PACKED_BYTES = 250_000_000
MAX_UNPACKED_BYTES = 500_000_000
DOWNLOAD_HOST = "db-ip.com"
_NAME = re.compile(r"^dbip-(city|asn)-lite-(\d{4}-\d{2})\.mmdb$")


class DatabaseError(Exception):
    """A file that is not the database it claims to be, or a failed download."""


@dataclass(frozen=True)
class Database:
    kind: str           # "city" or "asn"
    month: str          # "2026-10"
    path: Path
    bundled: bool = False

    @property
    def label(self) -> str:
        return f"DB-IP Lite {self.kind.upper() if self.kind == 'asn' else 'City'} {self.month}"


def data_dir() -> Path:
    return config.config_dir() / "data"


def _private_data_dir() -> Path:
    return config.private_dir(data_dir())


def _check(path: Path, kind: str, shown: str | None = None) -> str:
    """Open *path*; return its build month, or raise DatabaseError naming *shown*."""
    shown = shown or path.name
    try:
        import maxminddb
        reader = maxminddb.open_database(str(path))
        meta = reader.metadata()
        reader.close()
    except Exception as exc:  # noqa: BLE001 - any failure means "not this database"
        raise DatabaseError(f"{shown} is not a readable MaxMind DB file ({exc.__class__.__name__}).")
    if not str(meta.database_type).startswith(KINDS[kind]):
        raise DatabaseError(f"{shown} is a {meta.database_type} database, not DB-IP Lite "
                            f"{'City' if kind == 'city' else 'ASN'}.")
    return _dt.datetime.fromtimestamp(meta.build_epoch, _dt.timezone.utc).strftime("%Y-%m")


def installed(kind: str) -> Database | None:
    """The newest valid file of *kind* in the data folder."""
    found = []
    try:
        for entry in data_dir().iterdir():
            m = _NAME.match(entry.name)
            if m and m.group(1) == kind:
                found.append((m.group(2), entry))
    except OSError:
        return None
    for month, path in sorted(found, reverse=True):
        return Database(kind, month, path)
    return None


def _bundled_asn_month() -> str | None:
    try:
        return resources.files("routemap").joinpath("data/dbip-asn-lite.month").read_text().strip()
    except (OSError, FileNotFoundError):
        return None


def asn_database() -> Database | None:
    """The ASN database to use: a downloaded month if newer, else the bundled one
    (unpacked into the data folder on first use)."""
    current = installed("asn")
    bundled_month = _bundled_asn_month()
    if current and (bundled_month is None or current.month >= bundled_month):
        return current
    if bundled_month is None:
        return current
    target = data_dir() / f"dbip-asn-lite-{bundled_month}.mmdb"
    try:
        blob = resources.files("routemap").joinpath(BUNDLED_ASN).read_bytes()
        _install_bytes(gzip.decompress(blob), target, "asn")
    except (OSError, DatabaseError):
        return current
    _prune("asn", keep=target)
    return Database("asn", bundled_month, target, bundled=True)


def city_database() -> Database | None:
    return installed("city")


def _install_bytes(data: bytes, target: Path, kind: str) -> None:
    config.private_dir(target.parent)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        _check(Path(tmp), kind)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _prune(kind: str, keep: Path) -> None:
    """Remove older months of *kind*: one live copy is enough."""
    try:
        for entry in data_dir().iterdir():
            m = _NAME.match(entry.name)
            if m and m.group(1) == kind and entry != keep:
                entry.unlink()
    except OSError:
        pass


def import_file(source: str | os.PathLike, kind: str = "city") -> Database:
    """Install a .mmdb or .mmdb.gz the user chose (an air-gapped machine)."""
    src = Path(source)
    staging = data_dir() / f".import-{kind}.mmdb"
    _private_data_dir()
    try:
        if src.name.endswith(".gz"):
            with gzip.open(src, "rb") as fin, open(config.private_file(staging), "wb") as fout:
                written = 0
                while chunk := fin.read(1 << 20):
                    written += len(chunk)
                    if written > MAX_UNPACKED_BYTES:
                        raise DatabaseError(f"{src.name} unpacks to more than {_mb(MAX_UNPACKED_BYTES)}, "
                                            "larger than any DB-IP Lite file.")
                    fout.write(chunk)
        else:
            if src.stat().st_size > MAX_UNPACKED_BYTES:
                raise DatabaseError(f"{src.name} is larger than any DB-IP Lite file "
                                    f"(over {_mb(MAX_UNPACKED_BYTES)}).")
            shutil.copyfile(src, config.private_file(staging))
        month = _check(staging, kind, shown=src.name)
        target = data_dir() / f"dbip-{kind}-lite-{month}.mmdb"
        os.replace(staging, target)
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        raise DatabaseError(f"Could not read {src.name}: {exc}") from exc
    finally:
        if staging.exists():
            staging.unlink()
    _prune(kind, keep=target)
    return Database(kind, month, target)


def candidate_months(today: _dt.date | None = None) -> list[str]:
    """This month, then last month: DB-IP publishes on the first, and early in a
    month (or before their upload) only last month's file exists."""
    today = today or _dt.datetime.now(_dt.timezone.utc).date()
    first = today.replace(day=1)
    previous = (first - _dt.timedelta(days=1)).replace(day=1)
    return [first.strftime("%Y-%m"), previous.strftime("%Y-%m")]


def _mb(size: int) -> str:
    return f"{size / 1_000_000:,.0f} MB"


def _only_db_ip(request) -> None:
    """Every request of the download, the first and each redirect: https on db-ip.com only."""
    host = request.url.host or ""
    if request.url.scheme != "https" or not (host == DOWNLOAD_HOST or host.endswith("." + DOWNLOAD_HOST)):
        raise DatabaseError(f"The download was redirected to {request.url.scheme}://{host}, "
                            "not to https on db-ip.com; stopped.")


def download(kind: str, *, user_agent: str,
             progress: Callable[[int, int | None], None] | None = None,
             cancelled: Callable[[], bool] = lambda: False,
             transport=None, today: _dt.date | None = None) -> Database:
    """Fetch the newest monthly file of *kind*, check it, and make it live.

    *progress(done, total)* is called as bytes arrive; *cancelled()* is polled
    and stops the download cleanly. Sends one GET to download.db-ip.com with
    the app's User-Agent; nothing else.
    """
    import httpx

    _private_data_dir()
    last_error = None
    for month in candidate_months(today):
        url = URL.format(kind=kind, month=month)
        fd, tmp_gz = tempfile.mkstemp(prefix=f".dl-{kind}.", suffix=".gz", dir=data_dir())
        os.close(fd)
        try:
            with httpx.Client(transport=transport, timeout=DOWNLOAD_TIMEOUT, follow_redirects=True,
                              headers={"User-Agent": user_agent},
                              event_hooks={"request": [_only_db_ip]}) as client:
                with client.stream("GET", url) as response:
                    if response.status_code == 404:
                        last_error = f"{month} is not published yet"
                        continue
                    response.raise_for_status()
                    total = int(response.headers.get("content-length") or 0) or None
                    if total and total > MAX_PACKED_BYTES:
                        raise DatabaseError(f"The server offers {_mb(total)}, larger than any DB-IP Lite file.")
                    done = 0
                    with open(tmp_gz, "wb") as handle:
                        for chunk in response.iter_bytes(1 << 16):
                            if cancelled():
                                raise DatabaseError("Download cancelled.")
                            done += len(chunk)
                            if done > MAX_PACKED_BYTES:
                                raise DatabaseError("The download is larger than any DB-IP Lite file; stopped.")
                            handle.write(chunk)
                            if progress:
                                progress(done, total)
            return import_file(tmp_gz, kind)
        except httpx.HTTPError as exc:
            raise DatabaseError(f"Could not download DB-IP Lite {kind}: {exc.__class__.__name__}") from exc
        finally:
            try:
                os.unlink(tmp_gz)
            except OSError:
                pass
    raise DatabaseError(f"No DB-IP Lite {kind} file found ({last_error}).")


def is_stale(db: Database | None, today: _dt.date | None = None) -> bool:
    """Older than last month: time for "Update now"."""
    if db is None:
        return True
    return db.month < candidate_months(today)[1]
