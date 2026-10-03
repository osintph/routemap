"""scripts/testers.sh against a local stand-in for the download host (Linux only:
the real host is Linux, and the script uses GNU sed and OpenSSL's SHA-512 crypt)."""
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"),
                                reason="needs GNU sed and openssl passwd -6, as on the host")


def test_add_list_disable_enable_and_the_welcome_email(tmp_path):
    htpasswd = tmp_path / "testers.htpasswd"
    conf = tmp_path / "testers.env"
    conf.write_text(f"DOWNLOAD_HOST=unused\nHTPASSWD_FILE={htpasswd}\n"
                    f"DOWNLOAD_URL=https://downloads.example.org/\n"
                    f"GPG_FINGERPRINT='AAAA BBBB'\nFEEDBACK_EMAIL=beta@example.org\n")
    env = dict(os.environ, TESTERS_REMOTE_LOCAL="1", ROUTEMAP_TESTERS_ENV=str(conf),
               ROUTEMAP_TESTERS_LEDGER=str(tmp_path / "testers.csv"), PYTHON=sys.executable)
    run = lambda *a: subprocess.run(["bash", "scripts/testers.sh", *a], cwd=ROOT, env=env,
                                    capture_output=True, text=True)

    added = run("add", "--login", "jdoe", "--name", "Jane Doe", "--email", "jane@example.com")
    assert added.returncode == 0, added.stderr
    mail = added.stdout
    assert "Login:          jdoe" in mail and "https://downloads.example.org/" in mail
    assert "More info, then Run anyway" in mail and "AAAA BBBB" in mail
    assert "github.com/osintph/routemap/issues" in mail
    assert "licen" not in mail.lower().replace("open source (agpl-3.0)", "")
    password = next(l.split()[-1] for l in mail.splitlines() if l.startswith("Password:"))
    line = htpasswd.read_text().strip()
    assert line.startswith("jdoe:$6$") and password not in htpasswd.read_text()

    assert run("add", "--login", "jdoe", "--name", "J", "--email", "j@e").returncode != 0
    assert "jdoe" in run("list").stdout and "active" in run("list").stdout
    assert run("disable", "jdoe").returncode == 0
    assert htpasswd.read_text().startswith("#disabled:jdoe:")
    assert "disabled" in run("list").stdout
    enabled = run("enable", "jdoe")
    assert enabled.returncode == 0 and htpasswd.read_text().startswith("jdoe:$6$")
    assert run("add", "--login", "Bad Login!", "--name", "x", "--email", "x@y").returncode != 0
    assert (tmp_path / "testers.csv").read_text().count("jdoe") == 3
