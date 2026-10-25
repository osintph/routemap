import os
import pathlib
import shutil
import sys
import tempfile

import pytest

# The whole run, collection included, uses a config folder of its own: a test
# module that loads a fixture at import time runs before any fixture does
# (test_odin_run3_view.py unpacked the ASN database into the real folder),
# and a folder named by the developer's own ROUTEMAP_CONFIG_DIR is theirs too.
SESSION_CONFIG_DIR = tempfile.mkdtemp(prefix="routemap-tests-")
os.environ["ROUTEMAP_CONFIG_DIR"] = SESSION_CONFIG_DIR


def _real_folder() -> dict:
    """What is in the app's real config folder: path to (size, mtime)."""
    from routemap import config
    root = config._default_config_dir()
    if not root.is_dir():
        return {}
    return {str(f.relative_to(root)): (f.stat().st_size, f.stat().st_mtime_ns)
            for f in root.rglob("*") if f.is_file()}


_REAL_BEFORE = _real_folder()


def pytest_sessionfinish(session, exitstatus):
    """A run that wrote to the real config folder fails, whatever the tests
    said (Mac, 26 Oct 2026: settings and the ASN database written there)."""
    after = _real_folder()
    if after != _REAL_BEFORE:
        changed = sorted(k for k in set(after) | set(_REAL_BEFORE) if after.get(k) != _REAL_BEFORE.get(k))
        print(f"\nthe test run changed the real config folder: {', '.join(changed)}", file=sys.stderr)
        session.exitstatus = 1
    shutil.rmtree(SESSION_CONFIG_DIR, ignore_errors=True)

# Headless Qt for the GUI tests. Not on Windows: there the offscreen platform has
# no font database (text silently fails to render), while the native platform
# works on a CI runner with no window shown.
if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Every test gets its own empty config folder."""
    monkeypatch.setenv("ROUTEMAP_CONFIG_DIR", str(tmp_path / "cfg"))
    yield


@pytest.fixture(autouse=True)
def no_real_dns(monkeypatch, request):
    """No test resolves a name for real (0.5.0-beta.1: every trace resolves
    its target first). A name resolves to a documentation address of the
    family asked for, a literal to itself; DNS timing has no rows. A test that
    stubs these itself, or is marked real_dns, is left alone."""
    if request.node.get_closest_marker("real_dns"):
        yield
        return
    from routemap import probes

    def resolve(target, settings):
        import ipaddress
        try:
            ipaddress.ip_address(target)
            return {"name": target, "address": target, "family": 6 if ":" in target else 4, "by": "literal"}
        except ValueError:
            six = getattr(settings, "ip_version", "auto") == "6"
            return {"name": target, "address": "2001:db8::9" if six else "192.0.2.9", "family": 6 if six else 4,
                    "by": "system"}
    monkeypatch.setattr(probes, "resolve", resolve)
    monkeypatch.setattr(probes, "measure_dns", lambda target, settings, **kw: [])
    yield


def pytest_configure(config):
    config.addinivalue_line("markers", "real_dns: let the test resolve names for real")


# A test id is copied into the PYTEST_CURRENT_TEST environment variable, which
# Windows caps at 32767 characters and Linux at 128 KiB per string for a child
# process; a whole malformed file as a parameter id broke both in the engine.
MAX_NODEID = 1_000


def pytest_collection_modifyitems(items):
    long = [f"{item.nodeid[:80]}... ({len(item.nodeid)} chars)" for item in items
            if len(item.nodeid) > MAX_NODEID]
    if long:
        raise pytest.UsageError(f"test ids longer than {MAX_NODEID} characters; "
                                "give the parameters short ids:\n" + "\n".join(long))
