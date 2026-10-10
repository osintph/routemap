"""The CLI's --paths, --reverse and -4/-6 (0.4.0)."""
import json

import pytest

from routemap import cli, reverse, service
from routemap_engine import multipath


def test_cli_reverse_refuses_without_publish_my_ip(capsys, monkeypatch):
    monkeypatch.setattr(service, "run", lambda *a, **k: pytest.fail("nothing may be traced"))
    assert cli.main(["example.net", "--reverse", "--json", "--offline"]) == 2
    err = capsys.readouterr().err
    assert "publishes your public IP address" in err and "--publish-my-ip" in err


def test_publish_my_ip_alone_is_refused(capsys):
    with pytest.raises(SystemExit):
        cli.main(["example.net", "--publish-my-ip"])
    assert "--publish-my-ip goes with --reverse" in capsys.readouterr().err


def test_cli_reverse_agrees_only_for_its_own_run(monkeypatch, capsys):
    """--publish-my-ip is the run's consent; the window's stored consent is
    neither needed nor written."""
    from routemap import config
    from routemap_engine import OFFLINE, analyse_sync

    trace = "traceroute to x (62.115.0.9), 30 hops max\n 1  62.115.0.9  9.0 ms\n"
    monkeypatch.setattr(service, "run", lambda target, settings, **kw: type("R", (), {
        "text": trace, "argv": ["traceroute", target], "tool": "traceroute", "returncode": 0})())
    monkeypatch.setattr(reverse, "ready", lambda settings: (True, ""))

    async def plan(route, settings, **kw):
        return reverse.Plan(af=4, public_ip="62.115.7.7", probe={"id": 6012, "asn": 3320, "country": "DE"})
    seen = {}

    def run_sync(p, settings, **kw):
        seen.update(kw)
        return {"measurement_id": 9, "af": 4, "trace_text": trace, "probe": {"id": 6012},
                "route": analyse_sync(trace, sources=OFFLINE)}
    monkeypatch.setattr(reverse, "plan", plan)
    monkeypatch.setattr(reverse, "run_sync", run_sync)
    assert cli.main(["example.net", "--reverse", "--publish-my-ip", "--json", "--envelope", "--offline",
                     "--origin", "Manila, PH"]) == 0
    out, err = capsys.readouterr()
    assert seen == {"consent": True, "agreed_for_this_run": True}
    assert json.loads(out)["reverse"]["measurement_id"] == 9
    assert "RIPE Atlas measurements are public" in err and "62.115.7.7" in err
    assert not reverse.consented(config.load_settings())


@pytest.mark.parametrize("flag,family", [("-4", "4"), ("-6", "6")])
def test_family_flags_hold_the_trace_to_one_family(monkeypatch, flag, family):
    seen = {}

    class Done(Exception):
        pass

    def run(target, settings, **kw):
        seen["family"] = settings.ip_version
        raise Done
    monkeypatch.setattr(service, "run", run)
    with pytest.raises(Done):
        cli.main(["example.net", flag, "--json", "--offline", "--origin", "Manila, PH"])
    assert seen["family"] == family


def test_cli_paths_prints_the_hops_and_the_paths(monkeypatch, capsys):
    from tests.test_paths_gui import DST, Lab

    def discover(target, **kw):
        lab = Lab()
        return multipath.Discoverer(target, DST, lab, clock=lab.clock, options=kw.get("options")).run()
    monkeypatch.setattr(multipath, "discover", discover)
    monkeypatch.setattr(multipath, "available", lambda: (True, ""))
    assert cli.main(["example.net", "--paths", "--offline", "--origin", "Manila, PH"]) == 0
    out = capsys.readouterr().out
    rows = [line.split() for line in out.splitlines()]
    assert "at least 2 paths" in out and ["3a", "A"] in [r[:2] for r in rows] and ["3b", "B"] in [r[:2] for r in rows]
    assert '"At least": some load balancers do not spread ICMP probes.' in out
    assert any(line.startswith("A ") for line in out.splitlines())


def test_cli_paths_on_a_system_that_cannot_hold_a_flow_says_why(monkeypatch):
    monkeypatch.setattr(multipath, "available", lambda: (False, "Windows' ICMP API chooses each probe's identifier"))
    with pytest.raises(SystemExit) as exc:
        cli.main(["example.net", "--paths", "--offline", "--origin", "Manila, PH"])
    assert "cannot run on this system yet" in str(exc.value)
