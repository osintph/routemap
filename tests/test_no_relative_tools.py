"""No program is started by a bare name that the current folder or a relative
PATH entry could answer (RM-03, app side): the version line's git calls run
only inside a checkout, and only a git found in an absolute PATH folder."""
import json
import os
import subprocess
import sys

import pytest

from routemap import __about__ as about


@pytest.fixture
def hostile_cwd(tmp_path, monkeypatch):
    """A folder with its own git and git.exe, current and first on PATH as '.' and ''."""
    for name in ("git", "git.exe", "git.cmd", "git.bat"):
        fake = tmp_path / name
        fake.write_text("#!/bin/sh\necho planted\n")
        fake.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", os.pathsep.join([".", "", "bin", os.environ.get("PATH", "")]))
    started = []
    real = subprocess.run

    def spy(argv, *a, **k):
        started.append(list(argv))
        return real(argv, *a, **k)
    monkeypatch.setattr(subprocess, "run", spy)
    return tmp_path, started


def _check(started, cwd):
    for argv in started:
        exe = argv[0]
        assert os.path.isabs(exe), f"started by a bare name: {argv}"
        assert not os.path.realpath(exe).startswith(os.path.realpath(str(cwd))), f"started from the current folder: {argv}"


def test_the_source_checkout_commit_uses_an_absolute_git(hostile_cwd):
    cwd, started = hostile_cwd
    about.build_commit()
    _check(started, cwd)


def test_outside_a_checkout_no_git_runs_at_all(hostile_cwd, monkeypatch):
    cwd, started = hostile_cwd
    fake_pkg = cwd / "site" / "routemap"
    fake_pkg.mkdir(parents=True)
    monkeypatch.setattr(about, "__file__", str(fake_pkg / "__about__.py"))
    assert about.build_commit() == "unknown"
    assert started == []


def test_an_engine_installed_from_a_folder_is_asked_with_an_absolute_git(hostile_cwd, monkeypatch):
    cwd, started = hostile_cwd
    from importlib import metadata

    class Dist:
        def read_text(self, name):
            return json.dumps({"url": f"file://{cwd}", "dir_info": {}}) if name == "direct_url.json" else None
    monkeypatch.setattr(metadata, "distribution", lambda name: Dist())
    (cwd / ".git").mkdir()
    about.engine_commit_from_metadata()
    _check(started, cwd)
    started.clear()
    (cwd / ".git").rmdir()
    assert about.engine_commit_from_metadata() == "unknown" and started == []
