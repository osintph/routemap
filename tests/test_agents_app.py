"""Remote agents in the app (0.5.0-beta.1): the settings they are kept in, the
one ssh command a run starts, what happens on a failed connection, a cancel
or a hang, the analysis here of what came back, the masked first hops, and
the window's picker. No ssh connection is made: a fake process stands in."""
import io
import json
import threading
import time

import pytest

from routemap import agents, config

DST = "151.101.0.81"
HELLO = {"type": "hello", "engine": "0.8.0", "protocol": 1, "platform": "linux", "python": "3.12.3",
         "can": {"icmp4": True, "icmp6": False, "paths": False}, "tools": ["mtr"]}
TEXT = (f"traceroute to {DST} ({DST}), 30 hops max, 60 byte packets\n"
        " 1  _gateway (51.68.0.1)  0.2 ms\n 2  10.29.132.254  0.4 ms\n 3  51.68.15.4  2.0 ms\n"
        f" 4  62.115.1.1  9.0 ms\n 5  {DST}  10.0 ms\n")
RESULT = {"type": "result", "kind": "trace", "resolved": {"name": "bbc.com", "address": DST, "family": 4},
          "dns": [{"resolver": "system", "type": "A", "ms": 4.0, "addresses": [DST]}], "trace_text": TEXT,
          "tool": "mtr"}


class FakeProc:
    """ssh as Popen returns it, with the agent's output on stdout."""

    def __init__(self, lines, *, rc=0, stderr=b"", hang=False):
        payload = b"".join(json.dumps(m).encode() + b"\n" for m in lines)
        self.stdout = _Slow(payload) if hang else io.BytesIO(payload)
        self.stderr = io.BytesIO(stderr)
        self.stdin = io.BytesIO()
        self.rc, self.killed = rc, False

    def poll(self):
        return -9 if self.killed else (None if isinstance(self.stdout, _Slow) else self.rc)

    def wait(self):
        return -9 if self.killed else self.rc

    def kill(self):
        self.killed = True
        if isinstance(self.stdout, _Slow):
            self.stdout.closed_event.set()


class _Slow:
    """A stdout that sends the hello line and then nothing until killed."""

    def __init__(self, payload):
        self.first = payload.split(b"\n")[0] + b"\n"
        self.sent = False
        self.closed_event = threading.Event()

    def readline(self, n=-1):
        if not self.sent:
            self.sent = True
            return self.first
        self.closed_event.wait(10)
        return b""


def _popen(proc, seen):
    def popen(argv, **kw):
        seen["argv"], seen["kw"] = argv, kw
        return proc
    return popen


AGENT = agents.Agent("fra-vps", "fra-vps", place=agents.PLACE_CITY, city="Frankfurt am Main, DE", lat=50.11,
                     lon=8.68)


def _settings(**kw):
    return config.normalise(config.Settings(online_lookups=False, **kw))


def test_agents_in_settings_are_checked_and_unique():
    kept = agents.clean([{"name": "fra-vps", "destination": "fra-vps"},
                         {"name": "FRA-VPS", "destination": "other"},                  # same name
                         {"name": "x", "destination": "-oProxyCommand=evil"},
                         {"name": "y", "destination": "ok@host", "command": "rm -rf /"},
                         {"name": "<b>", "destination": "host"},
                         {"name": "z", "destination": "host", "place": "city"}])     # city without a place
    assert [a["name"] for a in kept] == ["fra-vps", "z"] and kept[1]["place"] == "ip"
    assert config.Settings().agents == []


def test_one_run_is_one_batch_mode_ssh_command(monkeypatch):
    seen = {}
    run = agents.run(AGENT, "trace", _settings(dns_resolvers=["9.9.9.9"]), target="bbc.com", ssh="/usr/bin/ssh",
                     popen=_popen(FakeProc([HELLO, RESULT]), seen))
    argv = seen["argv"]
    assert argv[:7] == ["/usr/bin/ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "--"]
    assert argv[7] == "fra-vps" and argv[8].startswith("routemap-engine agent 1 trace --target bbc.com")
    assert "--resolver 9.9.9.9" in argv[8] and "--stop-on-eof" in argv[8] and "--place" not in argv[8]
    assert run.result["trace_text"] == TEXT


def test_an_agent_placed_by_its_ip_asks_for_the_place_only_when_online_lookups_are_on():
    seen = {}
    a = agents.Agent("sgp", "sgp")
    agents.run(a, "hello", _settings(), ssh="ssh", popen=_popen(FakeProc([HELLO]), seen), online=True)
    assert seen["argv"][-1].endswith("--place ip")
    agents.run(a, "hello", _settings(), ssh="ssh", popen=_popen(FakeProc([HELLO]), seen), online=False)
    assert "--place" not in seen["argv"][-1]


def test_a_refused_connection_says_what_ssh_said_and_is_not_retried():
    calls = []

    def popen(argv, **kw):
        calls.append(argv)
        return FakeProc([], rc=255, stderr=b"debug1: x\r\nubuntu@host: Permission denied (publickey).\r\n")
    with pytest.raises(agents.AgentFailed, match=r"ssh could not connect to fra-vps: ubuntu@host: Permission "
                                                 r"denied \(publickey\)\."):
        agents.run(AGENT, "trace", _settings(), target="bbc.com", ssh="ssh", popen=popen)
    assert len(calls) == 1


def test_cancel_closes_the_session():
    proc = FakeProc([HELLO, RESULT], hang=True)
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(agents.AgentFailed, match="Stopped"):
        agents.run(AGENT, "trace", _settings(), target="bbc.com", ssh="ssh", popen=_popen(proc, {}), cancel=cancel)
    assert proc.killed and time.monotonic() - started < 5


def test_no_ssh_client_says_how_to_get_one(monkeypatch):
    monkeypatch.setattr(agents, "find_ssh", lambda: None)
    with pytest.raises(agents.AgentFailed, match="OpenSSH Client"):
        agents.run(AGENT, "hello", _settings())


def _remote(agent, proc_lines):
    run = agents.run(agent, "trace", _settings(), target="bbc.com", ssh="ssh", popen=_popen(FakeProc(proc_lines), {}))
    return agents.remote_result(agent, "trace", "bbc.com", run, _settings())


def test_a_remote_trace_starts_at_the_agent_with_the_providers_hops_masked():
    out = _remote(AGENT, [HELLO, RESULT])
    body = out["route"].to_dict()
    assert body["origin"]["lat"] == 50.11 and out["origin_how"] == "agent-city"
    assert out["agent"] == {"name": "fra-vps", "place": "Frankfurt am Main, DE", "first_hops_masked": True}
    masked = [h["hop"] for h in body["hops"] if h.get("masked")]
    assert masked == [1, 2, 3], masked
    text = json.dumps(body) + out["text"]
    assert "51.68.0.1" not in text and "51.68.15.4" not in text and "_gateway" not in text
    assert body["hops"][3]["address"] == "62.115.1.1" and body["resolved"]["address"] == DST


def test_show_first_hops_keeps_them():
    shown = agents.Agent(**dict(AGENT.to_dict(), show_first_hops=True))
    body = _remote(shown, [HELLO, RESULT])["route"].to_dict()
    assert not any(h.get("masked") for h in body["hops"]) and body["hops"][0]["address"] == "51.68.0.1"


def test_an_agent_without_a_place_and_offline_has_no_origin():
    a = agents.Agent("sgp", "sgp")
    out = _remote(a, [HELLO, RESULT])
    assert out["origin_how"] == "first-hop" and out["agent"]["place"] is None


# ------------------------------------------------------------- the window

@pytest.fixture
def window():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from routemap.gui.app import Controller
    from routemap.gui.mainwindow import MainWindow
    w = MainWindow()
    s = _settings(agents=[AGENT.to_dict()])
    c = Controller(w, s)
    yield w, c, app
    w.close()


def test_the_picker_lists_this_computer_then_each_agent(window):
    w, c, _ = window
    c._refresh_agents()
    assert [w.origin_picker.itemText(i) for i in range(w.origin_picker.count())] == \
        ["From: this computer", "From: fra-vps"]
    assert w.agent_name() is None and w.watch_button.isEnabled()
    w.origin_picker.setCurrentIndex(1)
    assert w.agent_name() == "fra-vps" and not w.watch_button.isEnabled()
    assert w.watch_button.toolTip() == "Live runs from this computer"
    w.set_agents([])
    assert w.agent_name() is None and w.origin_picker.isHidden()


def test_a_remote_result_names_the_agent_in_the_summary_and_the_origin(window):
    w, c, _ = window
    out = _remote(AGENT, [HELLO, RESULT])
    c._done(out, "bbc.com", "agent")
    assert "measured on fra-vps (agent)" in w.summary.text()
    assert "fra-vps system resolver" in w.summary.text()
    assert "fra-vps, Frankfurt am Main, DE" in w.origin_label.text() and "agent" in w.origin_label.text()
    assert not w.reverse_button.isVisible()


def test_an_interrupt_closes_the_session_at_once():
    """Ctrl+C in the CLI: the ssh process is killed, not waited for."""
    proc = FakeProc([HELLO, RESULT])

    def readline(n=-1):
        raise KeyboardInterrupt
    proc.stdout.readline = readline
    with pytest.raises(KeyboardInterrupt):
        agents.run(AGENT, "trace", _settings(), target="bbc.com", ssh="ssh", popen=_popen(proc, {}))
    assert proc.killed
