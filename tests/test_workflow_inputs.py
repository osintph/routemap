"""Workflow inputs never become shell text, and the diagnose script checks its
target and starts only absolute tools (RM-18, RM-03)."""
import importlib.util
import os
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UNTRUSTED = re.compile(r"\$\{\{\s*(inputs\.|github\.event\.|github\.head_ref|steps\.[^}]*outputs)")


def _run_blocks(text: str):
    """(line number, text) of every line inside a run: step, block or inline."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        indent, rest = lines[i].index("run:"), m.group(2)
        if rest and rest[0] not in "|>":
            yield i + 1, rest
            i += 1
            continue
        i += 1
        while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
            yield i + 1, lines[i]
            i += 1


@pytest.mark.parametrize("workflow", sorted((ROOT / ".github" / "workflows").glob("*.yml")), ids=lambda p: p.name)
def test_no_workflow_expands_an_input_into_a_shell_command(workflow):
    bad = [f"{workflow.name}:{n}: {line.strip()}" for n, line in _run_blocks(workflow.read_text(encoding="utf-8"))
           if UNTRUSTED.search(line)]
    assert not bad, bad


def _diagnose():
    spec = importlib.util.spec_from_file_location("diagnose", ROOT / "packaging" / "diagnose.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_diagnose_refuses_a_target_that_is_not_a_host_and_runs_nothing(monkeypatch):
    started = []
    monkeypatch.setattr(subprocess, "run", lambda argv, *a, **k: started.append(argv))
    d = _diagnose()
    for target in ("-I", "heise.de; id", "--help", "a b", "$(id)"):
        assert d.main(target) == 2, target
    assert started == []


TOOLS = ("tracert", "tracert.exe", "traceroute")


@pytest.mark.parametrize("system", ["windows", "posix"])
def test_diagnose_starts_trace_tools_by_absolute_path(monkeypatch, tmp_path, system):
    """With a planted tracert and traceroute in the current folder and '.' on PATH."""
    work, system32 = tmp_path / "work", tmp_path / "System32"
    work.mkdir(), system32.mkdir()
    for folder in (work, system32):
        for name in ("tracert.exe", "tracert.cmd", "traceroute"):
            (folder / name).write_text("planted")
            (folder / name).chmod(0o755)
    monkeypatch.chdir(work)
    monkeypatch.setenv("PATH", os.pathsep.join([".", ""]))
    started = []

    def spy(argv, *a, **k):
        started.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(subprocess, "run", spy)
    d = _diagnose()
    from routemap_engine import runner
    if system == "windows":
        monkeypatch.setattr(d.sys, "platform", "win32")
        monkeypatch.setattr(runner, "_platform", lambda: "windows")
        monkeypatch.setattr(runner, "_system32", lambda: str(system32))
    else:
        # A system folder of our own, so the test does not depend on the
        # machine having traceroute installed (CI runners do not).
        sbin = tmp_path / "sbin"
        sbin.mkdir()
        (sbin / "traceroute").write_text("system")
        (sbin / "traceroute").chmod(0o755)
        monkeypatch.setattr(runner, "SYSTEM_TOOL_DIRS", (str(sbin),))
        monkeypatch.setattr(runner, "EXTRA_TOOL_DIRS", ())
    d.main("heise.de")
    tools = [a for a in started if pathlib.PurePath(str(a[0])).name in TOOLS]
    assert tools, started
    for argv in tools:
        assert os.path.isabs(argv[0]) and not argv[0].startswith(str(work)), argv
    expected = system32 / "tracert.exe" if system == "windows" else tmp_path / "sbin" / "traceroute"
    assert all(argv[0] == str(expected) for argv in tools), tools
