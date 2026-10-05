import os
import sys

import pytest

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
