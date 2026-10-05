"""scripts/sign-windows.ps1 trusts nothing it has not checked (RM-05): the zip
and the installer must match the GPG-signed SHA256SUMS before anything is
unpacked, and the build's commit is read from BUILD-INFO.txt, never by running
the unsigned routemap-cli.exe. No PowerShell here, so this checks the script's
text; installers.yml's sign-check job runs it end to end on Windows."""
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts" / "sign-windows.ps1").read_text(encoding="utf-8")
CODE = "\n".join(line for line in SCRIPT.splitlines() if not line.lstrip().startswith("#"))
sys.path.insert(0, str(ROOT / "packaging"))


def test_the_signed_sums_are_required_and_checked_before_anything_is_unpacked():
    for param in ("Sums", "SumsSig"):
        assert re.search(rf"\[Parameter\(Mandatory = \$true\)\] \[string\] \${param}\b", CODE), param
    unpack = CODE.index("Expand-Archive")
    verify = CODE.find("--verify $SumsSig $Sums")
    compare = CODE.find("SHA256SUMS says")
    assert 0 < verify < unpack and 0 < compare < unpack
    assert "GOODSIG" in CODE


def test_nothing_from_the_unsigned_folder_is_run():
    assert not re.search(r"&\s*\(Join-Path \$folder", CODE)
    assert "--version" not in CODE
    assert "BUILD-INFO.txt" in CODE


def test_the_windows_folder_carries_its_commit(tmp_path):
    import assemble_windows
    commit = "0123456789abcdef0123456789abcdef01234567"
    path = assemble_windows.write_build_info(tmp_path, commit, "0.2.0-beta.3")
    assert path.read_text() == f"version=0.2.0-beta.3\ncommit={commit}\n"
    with pytest.raises(SystemExit):
        assemble_windows.write_build_info(tmp_path, "not-a-commit")


def test_the_ci_run_of_the_script_passes_the_signed_sums():
    wf = (ROOT / ".github" / "workflows" / "installers.yml").read_text(encoding="utf-8")
    assert "-Sums sums/SHA256SUMS -SumsSig sums/SHA256SUMS.asc" in wf and "-ReleaseKey" in wf
