"""What the app keeps about the user's traces is readable by the user only
(RM-11): the config folder and its data folder are 0700, and every file the
app writes there (settings, history, the three caches with SQLite's journal,
the DB-IP files, the site-code table) is 0600, under a umask of 022. A folder
made by an older version is tightened at start."""
import os
import stat
import sys
from importlib import resources

import pytest

from routemap import config, dbip, insight, service

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX modes")


@pytest.fixture
def default_home(tmp_path, monkeypatch):
    """The default config location (not the test override), under a temp HOME."""
    monkeypatch.delenv("ROUTEMAP_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    old = os.umask(0o022)
    insight._ASN = None
    service._CITY_READERS.clear()
    yield config.config_dir()
    os.umask(old)
    insight._ASN = None


def _modes(root):
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        found[dirpath] = stat.S_IMODE(os.stat(dirpath).st_mode)
        for name in filenames:
            path = os.path.join(dirpath, name)
            found[path] = stat.S_IMODE(os.lstat(path).st_mode)
    return found


def _loose(root):
    return {p: oct(m) for p, m in _modes(root).items()
            if m != (0o700 if os.path.isdir(p) else 0o600)}


def test_an_older_folder_is_tightened_at_start(default_home):
    root = default_home
    (root / "data").mkdir(parents=True)
    os.chmod(root, 0o755)
    os.chmod(root / "data", 0o755)
    for name in ("cache.sqlite3", "cache.sqlite3-wal", "history.json", "settings.json",
                 "ripe-cache.sqlite3", "ipgeo-cache.sqlite3", "site_codes.tsv", "data/dbip-asn-lite-2026-09.mmdb"):
        (root / name).write_text("x")
        os.chmod(root / name, 0o644)
    service.startup()
    assert not _loose(root), _loose(root)


def test_everything_the_app_writes_is_private(default_home, tmp_path):
    root = default_home
    s = config.Settings(history_enabled=True)
    config.save_settings(s)
    config.add_history({"target": "heise.de", "when": 1.0, "hops": 1, "placed": 0,
                        "route": {"hops": []}}, s)
    service.sources_for(s)
    insight.offline({"hops": [], "parser": "traceroute"}, s)
    insight.client(s, "t", service.SOURCEAPP)
    gz = tmp_path / "dbip-asn-lite-2026-10.mmdb.gz"
    gz.write_bytes(resources.files("routemap").joinpath(dbip.BUNDLED_ASN).read_bytes())
    dbip.import_file(gz, "asn")
    files = [p for p in _modes(root) if os.path.isfile(p)]
    assert any(p.endswith(".sqlite3") for p in files) and any(p.endswith(".mmdb") for p in files), files
    assert not _loose(root), _loose(root)
