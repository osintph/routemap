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
