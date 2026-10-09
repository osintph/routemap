"""routemap --watch: the table, the JSON at the end, and the limits it refuses to cross."""
import json

import pytest
from routemap_engine import probe, watch

from routemap import cli


@pytest.fixture
def network(monkeypatch):
    def fake_probe(dst, ttl, seq, wait):
        if ttl > 4:
            return probe.Reply(None, None)
        return probe.Reply(f"192.0.2.{ttl}", 3.0 * ttl, ttl == 4)
    monkeypatch.setattr(probe, "_probe", fake_probe)
    monkeypatch.setattr(probe, "available", lambda: (True, ""))
    monkeypatch.setattr(watch.socket, "gethostbyname", lambda host: "192.0.2.4")


def test_json_at_the_end_is_a_version_3_export(network, monkeypatch, capsys):
    monkeypatch.setattr(watch, "INTERVAL_MIN", 0.01)
    code = cli.main(["--watch", "example.net", "--count", "6", "--interval", "0.02", "--json", "--offline"])
    out, err = capsys.readouterr()
    assert code == 0
    doc = json.loads(out)
    assert doc["format_version"] == 3 and doc["session"]["cycles"] == 6
    assert doc["session"]["stopped_by"] == "count" and doc["trace"]["source"] == "watch"
    assert [h["hop"] for h in doc["session"]["hops"]] == [1, 2, 3, 4]
    assert "Loss%" in err            # the table goes to stderr when stdout is JSON


def test_without_json_the_table_is_printed(network, monkeypatch, capsys):
    monkeypatch.setattr(watch, "INTERVAL_MIN", 0.01)
    assert cli.main(["--watch", "example.net", "--count", "3", "--interval", "0.02", "--offline"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("Route Map watch to example.net")
    assert "Loss%" in out and "Path changes: none." in out


@pytest.mark.parametrize("extra,why", [
    (["--interval", "0.2"], "shortest it allows"),
    (["--interval", "120"], "out of range"),
    (["--duration", "1m"], "between 5 minutes and 8 hours"),
    (["--duration", "9h"], "between 5 minutes and 8 hours"),
    (["--duration", "soon"], "not a duration"),
    (["--count", "0"], "at least 1"),
])
def test_limits_are_refused_with_the_reason(network, capsys, extra, why):
    assert cli.main(["--watch", "example.net"] + extra) == 2
    assert why in capsys.readouterr().err


def test_watch_options_need_watch(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["example.net", "--interval", "2"])
    assert exc.value.code == 2 and "go with --watch" in capsys.readouterr().err


def test_no_prober_says_why(monkeypatch, capsys):
    monkeypatch.setattr(probe, "available", lambda: (False, "ping_group_range excludes this user"))
    assert cli.main(["--watch", "example.net"]) == 3
    assert "ping_group_range" in capsys.readouterr().err


@pytest.mark.parametrize("text,seconds", [("90", 90), ("90s", 90), ("10m", 600), ("2h", 7200), ("1.5h", 5400)])
def test_durations(text, seconds):
    assert cli.parse_duration(text) == seconds
