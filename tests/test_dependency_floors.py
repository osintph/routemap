"""No pinned or floored dependency admits a version with a published fix
missing (RM-16): Pillow decodes images in the tests and in the site build,
whose job holds the site deploy key."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
# package -> the first version with every published fix known at review time
FIXED = {"pillow": (12, 3, 0), "dnspython": (2, 6, 1)}


def _requirements():
    texts = {"pyproject.toml": (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
             "site/requirements.txt": (ROOT / "site" / "requirements.txt").read_text(encoding="utf-8")}
    for where, text in texts.items():
        for name, op, version in re.findall(r"(?im)\b([A-Za-z][A-Za-z0-9_.-]*)(?:\[[^\]]*\])?\s*(==|>=|~=)\s*([0-9][0-9.]*)", text):
            yield where, name.lower(), op, tuple(int(x) for x in version.split(".") if x.isdigit())


def test_no_requirement_admits_a_version_below_its_fix():
    loose = [f"{where}: {name}{op}{'.'.join(map(str, v))}" for where, name, op, v in _requirements()
             if name in FIXED and v < FIXED[name]]
    assert not loose, loose


def test_pillow_is_pinned_where_it_runs():
    found = {where for where, name, op, v in _requirements() if name == "pillow"}
    assert found == {"pyproject.toml", "site/requirements.txt"}, found
