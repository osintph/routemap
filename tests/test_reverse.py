"""Reverse traces (0.4.0): nothing runs without consent, consent can be
withdrawn and stays withdrawn, the plan targets the public IP of the traced
family from a probe near the destination, and the two directions are
compared by network, not by hop number."""
import asyncio
import json

import httpx
import pytest

from routemap import config, reverse
from routemap_engine import whereami


def hop(n, addr, asn=None, place=None, source="ip-db", lat=None, lon=None, cc=None):
    return {"hop": n, "address": addr, "addresses": [addr], "asn": asn, "place": place, "source": source,
            "lat": lat, "lon": lon, "cc": cc}


FORWARD = {"hops": [
    hop(1, "192.168.1.1", place="local", source="local"),
    hop(2, "122.2.187.146", 9299, "Manila, PH"),
    hop(3, "62.115.1.1", 1299, "Hong Kong, HK"),
    hop(4, "62.115.1.2", 1299, "Singapore, SG"),
    hop(5, "62.115.1.3", 1299, "Paris, FR"),
    hop(6, "62.115.1.4", 1299, "Frankfurt, DE"),
    hop(7, "193.99.144.80", 12306, "Hannover, DE", lat=52.37, lon=9.73, cc="DE"),
]}
# Probe -> user, so read backwards it goes user -> target. One extra hop
# (Mumbai) and Marseille instead of Paris.
REVERSE = {"hops": [
    hop(1, "193.99.144.1", 12306, "Hannover, DE"),
    hop(2, "62.115.2.4", 1299, "Frankfurt, DE"),
    hop(3, "62.115.2.5", 1299, "Marseille, FR"),
    hop(4, "62.115.2.6", 1299, "Mumbai, IN"),
    hop(5, "62.115.2.2", 1299, "Singapore, SG"),
    hop(6, "62.115.2.1", 1299, "Hong Kong, HK"),
    hop(7, "122.2.187.140", 9299, "Manila, PH"),
    hop(8, "203.0.113.47", place="local", source="local"),
]}


def test_forward_and_reverse_differences_are_marked_by_network():
    result = reverse.compare(FORWARD, REVERSE)
    differ = [r for r in result["rows"] if not r["same"]]
    assert [(r["forward"] and r["forward"]["place"], r["reverse"] and r["reverse"]["place"]) for r in differ] == \
        [("Paris, FR", "Mumbai, IN"), (None, "Marseille, FR")]
    same = [r["forward"]["place"] for r in result["rows"] if r["same"]]
    assert same == ["local", "Manila, PH", "Hong Kong, HK", "Singapore, SG", "Frankfurt, DE", "Hannover, DE"]
    assert result["summary"] == ("The paths differ between Singapore, SG and Frankfurt, DE: forward goes via "
                                 "Paris, FR, reverse via Mumbai, IN and Marseille, FR.")


def naive_compare(forward, reverse_route):
    """Hop i against hop i: what a side-by-side table without alignment shows."""
    fwd = forward["hops"]
    rev = list(reversed(reverse_route["hops"]))
    return [i for i in range(max(len(fwd), len(rev)))
            if i >= len(fwd) or i >= len(rev) or fwd[i]["place"] != rev[i]["place"]]


def test_a_naive_hop_by_hop_comparison_would_mark_the_shared_end_as_different():
    """The proof that alignment is needed: index by index, the extra reverse
    hop shifts everything after it, and Frankfurt and the destination's own
    network would be marked as differing, which they are not."""
    naive = naive_compare(FORWARD, REVERSE)
    assert len(naive) > 2
    aligned = reverse.compare(FORWARD, REVERSE)
    assert sum(not r["same"] for r in aligned["rows"]) == 2


def test_the_same_path_both_ways_says_so():
    back = {"hops": list(reversed([dict(h) for h in FORWARD["hops"]]))}
    result = reverse.compare(FORWARD, back)
    assert not result["differs"] and result["summary"] == "Both directions go through the same networks and places."


def settings(**kw):
    s = config.Settings(atlas_enabled=True, atlas_key="k", online_lookups=True)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_no_reverse_trace_runs_before_consent_or_after_withdrawal(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    calls = []
    transport = httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(201, json={"measurements": [1]}))
    p = reverse.Plan(af=4, public_ip="203.0.113.47", probe={"id": 1})
    s = settings()
    with pytest.raises(reverse.ReverseUnavailable):
        asyncio.run(reverse.run(p, s, consent=True, transport=transport))          # never agreed
    reverse.give_consent(s, "2026-10-10T04:00:00Z")
    with pytest.raises(reverse.ReverseUnavailable):
        asyncio.run(reverse.run(p, s, consent=False, transport=transport))         # this run not agreed
    reverse.withdraw_consent(s)
    with pytest.raises(reverse.ReverseUnavailable):
        asyncio.run(reverse.run(p, s, consent=True, transport=transport))          # withdrawn
    assert calls == []


def test_withdrawal_survives_a_restart(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    s = settings()
    reverse.give_consent(s, "2026-10-10T04:00:00Z")
    assert reverse.consented(config.load_settings())
    reverse.withdraw_consent(config.load_settings())
    assert not reverse.consented(config.load_settings())
    assert json.loads((tmp_path / "settings.json").read_text())["reverse_consent_at"] == ""


def test_the_plan_uses_the_traced_family_and_a_probe_near_the_destination(monkeypatch):
    asked = {}

    async def public_ip(**kw):
        asked["family"] = kw.get("family")
        return "2a02:2e0:3fe::47"

    async def asn_of(addr, **kw):
        return {"2a02:2e0:3fe::47": 3320}.get(addr, 12306)
    monkeypatch.setattr(whereami, "public_ip", public_ip)
    monkeypatch.setattr(whereami, "asn_of", asn_of)
    monkeypatch.setattr(reverse, "_offline_asn", lambda addr: None)
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        if request.url.path.endswith("/credits/"):
            return httpx.Response(200, json={"current_balance": 1000})
        return httpx.Response(200, json={"results": [
            {"id": 7, "asn_v6": 3320, "country_code": "DE", "geometry": {"coordinates": [9.7, 52.4]}},
            {"id": 8, "asn_v6": 12306, "country_code": "DE", "geometry": {"coordinates": [8.7, 50.1]}}]})
    route = {"hops": [hop(1, "2001:db8::1", source="local", place="local"),
                      hop(2, "2a02:2e0:3fe:1001:302::", None, "Hannover, DE", lat=52.37, lon=9.73, cc="DE")]}
    p = asyncio.run(reverse.plan(route, settings(), transport=httpx.MockTransport(handler)))
    assert asked["family"] == 6 and p.af == 6 and p.public_ip == "2a02:2e0:3fe::47"
    assert p.probe["id"] == 8 and p.user_asn == 3320 and p.dest_asn == 12306
    assert seen[0]["asn_v6"] == "12306" and seen[0]["tags"] == "system-ipv6-works"


def test_a_reverse_trace_needs_atlas_and_online_lookups():
    assert not reverse.ready(settings(atlas_key=""))[0]
    assert not reverse.ready(settings(online_lookups=False))[0]
    assert reverse.ready(settings())[0]


def test_the_consent_text_says_public_and_names_the_ip_and_the_cost():
    text = " ".join(reverse.consent_paragraphs("heise.de", "203.0.113.47"))
    for words in ("RIPE Atlas measurements are public", "203.0.113.47", "60 of your Atlas credits",
                  "cannot remove it afterwards", "withdraw this at any time in Settings › RIPE Atlas",
                  "origin coordinates are never sent"):
        assert words in text
