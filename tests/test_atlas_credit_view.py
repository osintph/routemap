"""What the Atlas dialog says about credits, for every state the engine returns.

Generalised over the states, not one answer: every Balance state maps to a
view, only a bad key and a short balance stop the trace, and no state that
carries no numbers ever shows one.
"""
import re

import pytest
from routemap_engine import atlas

from routemap import service

COST = atlas.TRACEROUTE_CREDITS


def view(**kw):
    return service.atlas_credit_view(atlas.Balance(**kw), COST)


def test_ok_shows_balance_cost_and_what_remains():
    v = view(state="ok", current=48320, daily_income=21600, daily_expenditure=1140)
    assert v["can_run"] and not v["fix_key"]
    rows = dict(v["lines"])
    assert rows["Your balance"] == "48,320 credits"
    assert rows["This trace"].startswith(f"{COST} credits")
    assert rows["After it"] == f"{48320 - COST:,} credits"
    assert "21,600" in rows["RIPE's estimate"] and "1,140" in rows["RIPE's estimate"]


def test_ok_without_estimates_leaves_the_row_out():
    assert "RIPE's estimate" not in dict(view(state="ok", current=500)["lines"])


@pytest.mark.parametrize("current,runs", [(COST, True), (COST - 1, False), (0, False)])
def test_a_balance_that_cannot_pay_stops_the_trace(current, runs):
    v = view(state="ok", current=current)
    assert v["can_run"] is runs
    assert v["state"] == ("ok" if runs else "low")


def test_bad_key_stops_the_trace_and_points_to_settings():
    v = view(state="bad_key", message="The provided API key does not exist")
    assert not v["can_run"] and v["fix_key"]
    text = v["lines"][0][1]
    assert "cannot run" in text and "Settings" in text and "does not exist" in text


def test_no_permission_lets_the_trace_run_and_hides_the_balance():
    v = view(state="no_permission", message="")
    assert v["can_run"] and not v["fix_key"]
    assert "credits read" in v["lines"][0][1]


def test_unavailable_lets_the_trace_run():
    v = view(state="unavailable")
    assert v["can_run"] and str(COST) in v["lines"][0][1]


@pytest.mark.parametrize("state", ["bad_key", "no_permission", "unavailable", "something new"])
def test_states_without_numbers_never_show_a_balance(state):
    v = view(state=state)
    text = " ".join(value for _, value in v["lines"])
    figures = {int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text)}
    assert figures <= {COST}


def test_no_em_dash_in_any_view():
    for kw in ({"state": "ok", "current": 9000, "daily_income": 1, "daily_expenditure": 2},
               {"state": "ok", "current": 1}, {"state": "bad_key", "message": "x"},
               {"state": "no_permission"}, {"state": "unavailable"}):
        assert chr(0x2014) not in repr(view(**kw))
