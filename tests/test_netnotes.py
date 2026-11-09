"""What the app says about adapters: only a tunnel gets the banner, what the
hop-1 check and the interception check say, the settings, the CLI and the help
text. Adapters are mocked; nothing is sent."""
import pathlib

import pytest

from routemap import cli, config, netnotes, service
from routemap_engine import interfaces as I

ROOT = pathlib.Path(__file__).resolve().parents[1]
TUNNEL = {"kind": "tunnel", "label": "Corp <tunnel>", "selected": False, "check": None}


def adapter(name, kind, up=True, addresses=("192.0.2.10",)):
    return I.Adapter(name, name, "", kind, up, 7, 7, False, list(addresses), [], [])


@pytest.mark.parametrize("kind", ["physical", "unclassified"])
def test_only_a_tunnel_gets_a_banner(kind):
    block = {**TUNNEL, "kind": kind}
    assert netnotes.banner(block) is None
    assert netnotes.notice_html(block, None, origin_auto=True) == ""
    assert netnotes.plain_lines(block, None, origin_auto=True) == []


def test_an_unclassified_adapter_is_still_in_the_details():
    assert netnotes.details_text({**TUNNEL, "kind": "unclassified", "label": "vSwitch"}) == "vSwitch (unclassified)"


def test_the_banner_wording():
    assert netnotes.banner({**TUNNEL, "label": "t0"}) == (
        "Traffic to this target goes through t0. The map shows the path through it, not the direct internet path.")
    assert netnotes.banner({**TUNNEL, "label": "t0"}, fresh=False).startswith("This trace went through t0.")


def test_origin_warning_needs_auto_and_a_tunnel_default_route():
    assert netnotes.origin_warning(True, True)
    assert netnotes.origin_warning(False, True) is None
    assert netnotes.origin_warning(True, False) is None


def test_a_target_through_a_tunnel_with_a_direct_default_route_gets_the_banner_only():
    """ODIN, 3-tailnet: a peer's 100.x address, no exit node, the public IP unchanged."""
    lines = netnotes.plain_lines(TUNNEL, None, origin_auto=True, internet_tunnel=False)
    assert len(lines) == 1 and lines[0].startswith("Traffic to this target goes through")
    assert "Origin is on Auto" not in netnotes.notice_html(TUNNEL, None, origin_auto=True, internet_tunnel=False)


def test_a_tunnel_default_route_warns_even_when_this_target_goes_direct():
    block = {"kind": "physical", "label": "eth0", "selected": True, "check": "consistent"}
    lines = netnotes.plain_lines(block, None, origin_auto=True, internet_tunnel=True)
    assert len(lines) == 1 and lines[0].startswith("Origin is on Auto")
    assert netnotes.LINK_ORIGIN in netnotes.notice_html(block, None, origin_auto=True, internet_tunnel=True)


def _route_table(routes):
    """interfaces.used_for over mocked adapters: *routes* maps a destination to the adapter it routes through."""
    eth = I.Adapter("eth0", "eth0", "", "physical", True, 2, 2, False, ["192.0.2.10"], [], [])
    tun = I.Adapter("t0", "t0", "", "tunnel", True, 3, 3, False, ["198.51.100.2"], [], [])
    by_name = {"eth0": eth, "t0": tun}

    def source(address):
        if address not in routes:
            raise OSError("no route")
        return by_name[routes[address]].addresses[0]
    return lambda address: I.used_for(address, list_fn=lambda: [eth, tun], source_for=source)


@pytest.mark.parametrize("routes,want", [
    ({"192.0.2.1": "eth0", "2001:db8::1": "eth0"}, False),   # a split tunnel: only some targets use it
    ({"192.0.2.1": "eth0"}, False),                          # no IPv6 route at all
    ({"192.0.2.1": "t0", "2001:db8::1": "eth0"}, True),
    ({"192.0.2.1": "eth0", "2001:db8::1": "t0"}, True),
    ({}, False)])
def test_internet_via_tunnel_reads_the_route_to_the_internet(routes, want):
    assert netnotes.internet_via_tunnel(_route_table(routes)) is want


def test_internet_via_tunnel_asks_for_addresses_nobody_owns():
    import ipaddress
    from routemap_engine.netaddr import is_private_ip
    assert all(is_private_ip(a) and ipaddress.ip_address(a) for a in netnotes.EGRESS_ADDRESSES)


def test_the_notice_escapes_an_adapters_name_and_links_the_alternatives():
    text = netnotes.notice_html(TUNNEL, None, origin_auto=True, internet_tunnel=True)
    assert "<tunnel>" not in text and "&lt;tunnel&gt;" in text
    for href in (netnotes.LINK_HELP, netnotes.LINK_AGENTS, netnotes.LINK_REVERSE, netnotes.LINK_ORIGIN):
        assert href in text


def test_the_check_lines():
    chosen = {"kind": "physical", "label": "eth0", "selected": True}
    assert netnotes.check_line({**chosen, "check": "consistent"}) is None
    assert netnotes.check_line({**chosen, "check": "redirected", "redirected_by": "t0"}) == (
        "Probes were redirected by t0; the selected interface was not used.")
    assert "Could not confirm" in netnotes.check_line({**chosen, "check": "unconfirmed"})
    assert "has no route" in netnotes.check_line({**chosen, "check": "no_route"})
    assert netnotes.check_line({**chosen, "selected": False, "check": "redirected"}) is None


@pytest.mark.parametrize("condition,words", [("connect_completed_at_ttl_1", "completed at TTL 1"),
                                             ("connect_refused_at_ttl_2", "refused at TTL 2")])
def test_the_interception_line_says_what_happened(condition, words):
    paths = {"interception": {"intercepted": True, "condition": condition, "guard": None, "split_hop1": None}}
    assert words in netnotes.interception_line(paths)
    text = netnotes.notice_html(None, paths)
    assert "unreliable" in text and netnotes.LINK_AGENTS in text and netnotes.LINK_REVERSE in text


def test_a_guarded_result_is_not_called_interception():
    paths = {"interception": {"intercepted": False, "condition": "connect_completed_at_ttl_1",
                              "guard": "target_on_local_subnet", "split_hop1": None}}
    assert netnotes.interception_line(paths) is None and netnotes.notice_html(None, paths) == ""


def test_a_split_line_only_when_the_engine_reports_one():
    assert netnotes.split_line({"interception": {"split_hop1": None}}) is None
    line = netnotes.split_line({"interception": {"split_hop1": {"tcp": "192.0.2.1", "icmp": "198.51.100.1"}}})
    assert "192.0.2.1" in line and "198.51.100.1" in line


def test_the_block_kept_in_memory_and_what_is_stored():
    use = I.InterfaceUse("tunnel", "t0", addresses=["192.0.2.10"], gateways=["192.0.2.1"])
    block = netnotes.block_of(use)
    assert block["addresses"] == ["192.0.2.10"]
    assert "addresses" not in netnotes.stored(block) and "gateways" not in netnotes.stored(block)
    assert netnotes.block_of(None) is None and netnotes.stored(None) is None


def test_bypass_notice_needs_a_physical_choice_and_a_live_tunnel():
    eth, tun = adapter("eth0", "physical"), adapter("t0", "tunnel")
    assert netnotes.bypass_applies(eth, [eth, tun])
    assert not netnotes.bypass_applies(tun, [eth, tun])
    assert not netnotes.bypass_applies(eth, [eth])
    assert not netnotes.bypass_applies(eth, [eth, adapter("t1", "tunnel", up=False)])
    assert not netnotes.bypass_applies(None, [eth, tun])


# -------------------------------------------------------------------- settings ---

def test_automatic_is_the_default_for_new_installs_and_upgrades():
    assert config.Settings().probe_interface == ""
    path = config.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"tool": "auto", "saved_by": "0.5.0-beta.4"}', encoding="utf-8")
    assert config.load_settings().probe_interface == ""


def test_the_choice_persists():
    settings = config.Settings(probe_interface="{guid}", probe_interface_name="Ethernet")
    config.save_settings(settings)
    loaded = config.load_settings()
    assert (loaded.probe_interface, loaded.probe_interface_name) == ("{guid}", "Ethernet")


@pytest.mark.parametrize("bad", [5, "x" * 301, "a\nb", None])
def test_a_hand_edited_interface_falls_back_to_automatic(bad):
    settings = config.normalise(config.Settings(probe_interface=bad, probe_interface_name="n"))
    assert settings.probe_interface == "" and settings.probe_interface_name == ""


def test_trace_options_pass_the_interface():
    assert service.trace_options(config.Settings(), "icmp").interface is None
    assert service.trace_options(config.Settings(probe_interface="en0"), "icmp").interface == "en0"


# ------------------------------------------------------------------------- CLI ---

def test_list_interfaces_prints_the_oss_list(monkeypatch, capsys):
    monkeypatch.setattr(I, "list_adapters", lambda: [adapter("eth0", "physical"), adapter("t0", "tunnel", up=False)])
    assert cli.main(["--list-interfaces"]) == 0
    out = capsys.readouterr().out
    assert "  eth0, physical, up, 192.0.2.10" in out and "- t0, tunnel, down" in out


def test_interface_is_refused_with_an_agent(capsys):
    with pytest.raises(SystemExit):
        cli.main(["example.com", "--from", "a", "-i", "en0"])
    assert "--from does not go with --interface" in capsys.readouterr().err


def test_dash_i_is_for_this_run_and_the_notice_shows_once(monkeypatch, capsys):
    import argparse
    eth, tun = adapter("eth0", "physical"), adapter("t0", "tunnel")
    monkeypatch.setattr(I, "list_adapters", lambda: [eth, tun])
    settings = config.load_settings()
    cli._chosen_interface(argparse.Namespace(interface="eth0"), settings)
    assert settings.probe_interface == "eth0" and "may bypass" in capsys.readouterr().err
    assert config.load_settings().probe_interface == "" and config.load_settings().bypass_notice_seen
    cli._chosen_interface(argparse.Namespace(interface="eth0"), config.load_settings())
    assert "may bypass" not in capsys.readouterr().err


# ------------------------------------------------------------------- help, names ---

def test_the_help_is_the_same_text_as_the_guide():
    help_text = (ROOT / "routemap/gui/data/help/vpn-sase.md").read_text("utf-8").strip()
    assert help_text.replace("{NAME}", "Route Map") in (ROOT / "docs/guide.md").read_text("utf-8")


VENDORS = ("zscaler", "netskope", "globalprotect", "palo alto", "cloudflare warp", "tailscale", "wireguard", "openvpn",
           "fortinet", "forticlient", "anyconnect", "cisco", "hyper-v", "vethernet", "wintun", "utun")


@pytest.mark.parametrize("path", ["routemap/netnotes.py", "routemap/gui/data/help/vpn-sase.md"])
def test_no_vendor_or_adapter_name_in_the_wording(path):
    text = (ROOT / path).read_text("utf-8").lower()
    assert not [v for v in VENDORS if v in text]
