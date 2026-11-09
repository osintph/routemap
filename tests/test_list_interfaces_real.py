"""Not mocked: --list-interfaces on the machine running the tests, so the real
enumeration runs on the Linux, macOS and Windows CI runners. It reads the OS's
adapter list and sends nothing."""
import re
import subprocess
import sys

ROW = re.compile(r"^[- ] .+, (physical|tunnel|unclassified), (up|down)(, .+)?$", re.M)


def test_list_interfaces_runs_and_lists_an_adapter_with_a_kind():
    done = subprocess.run([sys.executable, "-m", "routemap.cli", "--list-interfaces"],
                          capture_output=True, timeout=120)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert ROW.search(done.stdout.decode("utf-8").replace("\r\n", "\n")), done.stdout
