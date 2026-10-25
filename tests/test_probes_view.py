"""DNS timing, port tests and the Paths heading as the app shows them
(0.5.0-beta.1): the words, the settings, the CLI and the exports. Nothing here
sends a packet: the engine's lookups and connects are replaced."""
import json
import socket

import pytest

from routemap import cli, config, imported, probes, service

BBC = "151.101.0.81"
SYSTEM_A = {"resolver": "system", "type": "A", "ms": 18.2, "addresses": [BBC, "151.101.64.81"], "rcode": None,
            "aa": None, "cached": None, "ttl": None, "error": None, "tcp": False}
SYSTEM_AAAA_EMPTY = {"resolver": "system", "type": "AAAA", "ms": None, "addresses": [], "rcode": None, "aa": None,
                     "cached": None, "ttl": None,
                     "error": "system resolver returned no IPv6 address (this computer may have no IPv6)",
                     "tcp": False}
QUAD9_A = {"resolver": "9.9.9.9", "type": "A", "ms": 36.0, "addresses": [BBC], "rcode": "NOERROR", "aa": False,
           "cached": None, "ttl": 212, "error": None, "tcp": False}
RESOLVED = {"name": "bbc.com", "address": BBC, "family": 4, "by": "system"}
PORTS = {"address": BBC, "cap": 32, "parallel": 4, "wait": 3.0, "wait_used": 1.0, "seconds": 1.1,
         "results": [{"port": 443, "state": "open", "reason": None, "connect_ms": 9.1, "tls_ms": 23.4,
                      "tls_version": "TLSv1.3", "tls_error": None, "waited": None},
                     {"port": 80, "state": "open", "reason": None, "connect_ms": 9.0, "tls_ms": None,
                      "tls_version": None, "tls_error": None, "waited": None},
                     {"port": 22, "state": "filtered", "reason": "no answer (the system gave up after 1.0 s)",
                      "connect_ms": None, "tls_ms": None, "tls_version": None, "tls_error": None, "waited": 1.0},
                     {"port": 53, "state": "closed", "reason": "reset", "connect_ms": None, "tls_ms": None,
                      "tls_version": None, "tls_error": None, "waited": None}]}


# ------------------------------------------------------------- the words

def test_the_summary_line_names_the_traced_address_and_the_system_time():
    assert probes.dns_line(RESOLVED, [SYSTEM_A, SYSTEM_AAAA_EMPTY, QUAD9_A]) == \
        "bbc.com resolved to 151.101.0.81 in 18 ms (system resolver)"
    assert probes.dns_line({"name": BBC, "address": BBC, "family": 4, "by": "literal"}, []) == \
        f"Traced address {BBC}"
    assert probes.ports_line(PORTS) == "ports: 443 open 9.1 ms, 80 open, 53 closed, 1 filtered"
    shut = dict(PORTS, results=[r for r in PORTS["results"] if r["state"] == "filtered"])
    assert probes.ports_line(shut) == "ports: all 1 filtered"


def test_dns_rows_never_claim_a_record_is_missing_and_say_what_is_not_stated():
    rows = probes.dns_rows([SYSTEM_A, SYSTEM_AAAA_EMPTY, QUAD9_A])
    assert rows[0][:5] == ["System resolver", "A", "18 ms", "2 addresses", "not stated"]
    assert rows[1][3] == "system resolver returned no IPv6 address (this computer may have no IPv6)"
    assert rows[2][3:7] == ["NOERROR", "no", "not stated", "212 s"]
    assert not any("record" in cell for row in rows for cell in row)


def test_the_ports_note_says_when_the_system_waited_less_than_asked():
    note = probes.ports_note(PORTS)
    assert "not a port scanner" in note and "about 1 s, not the 3 s set in Settings" in note
    assert "not the" not in probes.ports_note(dict(PORTS, wait_used=3.0))
    rows = probes.port_rows(PORTS)
    assert rows[0] == ["443", "open", "9.1 ms", "23 ms"] and rows[2][1].startswith("filtered (no answer")


def _disc(**kw):
    base = {"method": "tcp-paris", "port": 443, "af": 4, "stopped_by": "complete", "stop_text": "complete",
            "resolved": dict(RESOLVED), "paths": [{"id": "A", "reached": True, "reached_by": "discovery",
                                                    "sent": 10, "lost": 0, "flows": [0], "hops": []}]}
    base.update(kw)
    return base


def test_the_paths_heading_says_where_discovery_stopped_and_what_full_ttl_found():
    disc = _disc(stopped_by="gap", stop_text="stopped after 5 silent hops (3 to 7)", silent_stop=[3, 7],
                 paths=[{"id": "A", "reached": True, "reached_by": "full_ttl", "sent": 10, "lost": 5}])
    lines = probes.paths_lines(disc)
    assert lines[0] == "bbc.com resolved to 151.101.0.81"
    assert lines[1] == ("Discovery stopped after 5 silent hops (3 to 7). The target was then asked at full TTL: "
                        "reached on all 1 paths found.")
    assert lines[2] == ("Path A: the target answered 5 of 10 attempts; some servers answer fewer after the "
                        "discovery's probes.")
    many = dict(disc, paths=[{"id": x, "reached": True, "reached_by": "full_ttl", "sent": 10, "lost": n}
                             for x, n in zip("ABC", (9, 8, 7))])
    assert probes.paths_lines(many)[2] == ("On 3 paths the target answered 1 to 3 of 10 attempts each; some "
                                           "servers answer fewer after the discovery's probes.")


def test_tcp_silence_has_two_wordings_by_who_answered_the_icmp_check():
    routers = probes.paths_lines(_disc(stopped_by="gap", silent_stop=[3, 7], tcp_silent_from=3,
                                       tcp_silent_by="router"))
    assert ("Routers on this network do not answer TCP probes beyond hop 2; Paths cannot map past it here; "
            "Trace (ICMP) can.") in routers
    target = probes.paths_lines(_disc(stopped_by="gap", silent_stop=[15, 19], tcp_silent_from=15,
                                      tcp_silent_by="target"))
    assert ("The target answers ICMP at hop 15 but its TCP service answered only at full TTL; a firewall or "
            "load balancer in front of the target is likely.") in target
    assert not any("Routers on this network" in line for line in target)


def test_a_paths_run_shows_the_traces_address_when_they_differ():
    """bbc.com on 0.4.0-beta.2: Paths resolved 151.101.0.81, the Trace before 151.101.192.81."""
    lines = probes.paths_lines(_disc(), trace_resolved=dict(RESOLVED, address="151.101.192.81"))
    assert lines[0] == "bbc.com resolved to 151.101.0.81 (Trace resolved 151.101.192.81)"
    assert probes.paths_lines(_disc(), trace_resolved=dict(RESOLVED))[0] == "bbc.com resolved to 151.101.0.81"


def test_an_unreached_path_is_told_apart_by_the_port_test():
    disc = _disc(paths=[{"id": "A", "reached": False, "reached_by": None, "sent": 10, "lost": 10}])
    assert ("Port 443 answered (open, 9.1 ms): the target is up; the routers in between do not answer."
            in probes.paths_lines(disc, ports=PORTS))
    shut = dict(PORTS, results=[dict(PORTS["results"][2], port=443)])
    assert "Port 443 did not answer either (filtered)." in probes.paths_lines(disc, ports=shut)


# ------------------------------------------------------------- settings

def test_settings_drop_bad_resolvers_and_ports_and_clamp_the_wait():
    s = config.Settings(dns_resolvers=["9.9.9.9", "dns.google", "9.9.9.9", "10.0.0.53"],
                        port_list="1-1024", tls_ports="443, 8443", port_wait=99)
    config.normalise(s)
    assert s.dns_resolvers == ["9.9.9.9", "10.0.0.53"]
    assert s.port_list == "443, 80, 22, 25, 53, 3389" and s.tls_ports == "443, 8443" and s.port_wait == 10.0
    assert config.Settings().ports_with_trace is False and config.Settings().live_dns is False
    assert config.Settings().dns_resolvers == []


# ------------------------------------------------------------- the trace job

def test_the_trace_goes_to_the_address_the_dns_step_resolved(monkeypatch):
    from routemap.gui import app
    seen = {}
    monkeypatch.setattr(probes, "resolve", lambda target, settings: dict(RESOLVED))
    monkeypatch.setattr(probes, "measure_dns", lambda target, settings: [SYSTEM_A])

    def run(target, settings, **kw):
        seen.update(kw)
        from routemap_engine.runner import TraceResult
        text = f"traceroute to {BBC} ({BBC}), 30 hops max, 60 byte packets\n 1  {BBC}  5.0 ms\n"
        kw["on_line"](text.splitlines()[0])
        kw["on_line"](text.splitlines()[1])
        return TraceResult(text=text, tool="traceroute", argv=["traceroute", BBC], returncode=0, address=BBC)
    monkeypatch.setattr(service, "run", run)
    s = config.Settings(online_lookups=False)
    out = app.progressive_trace("bbc.com", s, None, on_line=lambda line: None, on_progress=lambda *a: None,
                                on_hop=lambda r: None, cancel=None)
    assert seen["address"] == BBC
    body = out["route"].to_dict()
    assert body["resolved"]["address"] == BBC and body["dns"] == [SYSTEM_A] and "ports" not in body


# ------------------------------------------------------------- CLI

def test_cli_refuses_port_ranges_and_bad_resolvers(capsys):
    assert cli.main(["bbc.com", "--ports", "1-1024"]) == 2
    assert "not a port scanner" in capsys.readouterr().err
    assert cli.main(["bbc.com", "--dns", "--resolver", "dns.google"]) == 2
    assert "not an IP address" in capsys.readouterr().err


def test_cli_dns_and_ports_print_their_tables(monkeypatch, capsys):
    monkeypatch.setattr(probes, "resolve", lambda target, settings: dict(RESOLVED))
    monkeypatch.setattr(probes, "measure_dns", lambda target, settings: [SYSTEM_A, QUAD9_A])
    monkeypatch.setattr(probes, "check_ports", lambda address, target, settings, ports=None: PORTS)
    assert cli.main(["bbc.com", "--dns", "--ports"]) == 0
    out = capsys.readouterr()
    assert "bbc.com resolved to 151.101.0.81 in 18 ms (system resolver)" in out.err
    assert "NOERROR, not authoritative, TTL 212 s" in out.out
    assert f"Ports to {BBC} (from this computer; one connection attempt each, at most 32)" in out.out


def test_cli_from_an_unknown_agent_names_the_ones_there_are(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "load_settings", lambda: config.normalise(config.Settings(
        agents=[{"name": "fra-vps", "destination": "fra-vps"}])))
    with pytest.raises(SystemExit) as exc:
        cli.main(["bbc.com", "--from", "nope", "--json"])
    assert "no agent named 'nope'; agents: fra-vps" in str(exc.value)
    with pytest.raises(SystemExit):
        cli.main(["bbc.com", "--from", "fra-vps", "--watch"])


# ------------------------------------------------------------- exports

def _route_with_probes():
    from routemap_engine import OFFLINE, analyse_sync
    route = analyse_sync(f"traceroute to {BBC} ({BBC}), 30 hops max\n 1  {BBC}  5.0 ms\n", None, sources=OFFLINE)
    route.resolved, route.dns, route.ports = dict(RESOLVED), [SYSTEM_A, SYSTEM_AAAA_EMPTY, QUAD9_A], PORTS
    return route.to_dict()


def test_format_5_carries_dns_ports_and_the_agent_and_reads_back():
    body = _route_with_probes()
    doc = json.loads(service.export_json(body, target="bbc.com", trace_text="", argv=None, source="agent",
                                         origin_how="agent-city",
                                         agent={"name": "fra-vps", "place": "Frankfurt am Main, DE",
                                                "first_hops_masked": True, "address": "203.0.113.77"}))
    assert doc["format_version"] == 5
    assert doc["agent"] == {"name": "fra-vps", "place": "Frankfurt am Main, DE", "first_hops_masked": True}
    back = imported.export(doc)
    assert back["agent"]["name"] == "fra-vps" and back["source"] == "agent" and back["origin_how"] == "agent-city"
    assert back["route"]["resolved"]["address"] == BBC and back["route"]["ports"]["results"][0]["port"] == 443
    assert [r["type"] for r in back["route"]["dns"]] == ["A", "AAAA", "A"]


def test_the_png_title_has_the_address_and_the_dns_time_and_no_ports():
    from routemap.gui import app
    title = app.png_title(_route_with_probes(), "bbc.com")
    assert title.startswith(f"bbc.com ({BBC}) from ") and "DNS 18 ms" in title and "443" not in title
    assert app.png_title(_route_with_probes(), "bbc.com", {"name": "fra-vps"}).startswith(
        f"bbc.com ({BBC}) from fra-vps (agent)")


@pytest.mark.real_dns
@pytest.mark.parametrize("online,expected", [(False, []), (True, ["9.9.9.9"])])
def test_online_lookups_off_asks_only_the_system_resolver(monkeypatch, online, expected):
    """Help > Privacy lists DNS timing under Online lookups: off, the added
    resolvers are not asked (the engine's lookups are replaced here)."""
    from routemap_engine import dnstime
    asked = []
    monkeypatch.setattr(dnstime, "measure", lambda target, resolvers, **kw: asked.append(list(resolvers)) or [])
    probes.measure_dns("bbc.com", config.Settings(dns_resolvers=["9.9.9.9"], online_lookups=online))
    assert asked == [expected]


def test_ctrl_c_on_a_remote_run_ends_cleanly(monkeypatch, capsys):
    from routemap import agents
    monkeypatch.setattr(config, "load_settings", lambda: config.normalise(config.Settings(
        agents=[{"name": "fra-vps", "destination": "fra-vps"}])))

    def run(*a, **kw):
        raise KeyboardInterrupt
    monkeypatch.setattr(agents, "run", run)
    with pytest.raises(SystemExit) as exc:
        cli.main(["bbc.com", "--from", "fra-vps", "--json"])
    assert exc.value.code == 130 and "the ssh session to fra-vps was closed" in capsys.readouterr().err
