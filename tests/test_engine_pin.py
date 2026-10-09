"""The app runs on one engine release, pinned by hash (the security review's
Part 3): pyproject.toml and the lock name the same version, the lock carries
the hashes of that release's PyPI files, and the release build and the tests
install from the lock with --require-hashes."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
# routemap-engine 0.5.0 on PyPI, the same bytes as the GitHub release files
# (compared 2026-10-09).
ENGINE_RELEASE = "0.5.0"
ENGINE_HASHES = {"2af49b482000cd0d093377de876b0a135da8342b7de22b8c8dafb0272ee6a7a2",   # wheel
                 "d214b7cbfc98e65cedfeeab068ce6a7381bbd5b6ea3b4952a8fa9d1a62aace38"}   # sdist


def _lock() -> str:
    return (ROOT / "requirements" / "app.txt").read_text(encoding="utf-8")


def test_pyproject_and_the_lock_pin_the_same_engine_release():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pin = re.search(r'"routemap-engine\[offline\]==([0-9][^"]*)"', pyproject)
    locked = re.search(r"^routemap-engine==(\S+)", _lock(), flags=re.M)
    assert pin and locked and pin.group(1) == locked.group(1) == ENGINE_RELEASE, (pin, locked)


def test_the_lock_carries_the_release_files_hashes():
    block = re.search(r"^routemap-engine==\S+((?:\s*\\\n\s+--hash=sha256:[0-9a-f]{64})+)", _lock(), flags=re.M)
    assert block and set(re.findall(r"[0-9a-f]{64}", block.group(1))) == ENGINE_HASHES
    pins = re.findall(r"^([A-Za-z0-9_.-]+)==", _lock(), flags=re.M)
    assert len(pins) >= 10 and all(re.search(rf"^{re.escape(p)}==[^\n]* \\\n\s+--hash=sha256:", _lock(), flags=re.M)
                                   for p in pins)


def test_the_release_build_and_the_tests_install_from_the_lock():
    for workflow in ("build.yml", "tests.yml"):
        text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        assert "pip install --require-hashes -r requirements/app.txt" in text, workflow
    build = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    # The app itself adds nothing to what the lock installed.
    assert re.search(r"pip install --no-deps (--no-build-isolation )?(\.|\"\.\[gui\]\")\s*$", build, flags=re.M)
