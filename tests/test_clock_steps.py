"""A change of the system clock during Watch (engine 0.8.2, routemap-engine #24,
reported on Bluesky by sasame-mcp.bsky.social): the cycle is kept and the
change is said plainly wherever gaps are shown (the live note, the PDF, the
CLI table, the JSON); a session that cannot tell sleep from a clock change
says that once, in the same places. Engine sessions run on injected clocks;
nothing is sent."""
import json
import logging
import time
from concurrent.futures import Future

import pytest
from routemap_engine import probe, watch

from routemap import cli, imported, live, service


class SyncPool:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args):
        f = Future()
        f.set_result(fn(*args))
        return f


def _session(monkeypatch, *, jumps, boot=True, cycles=40):
    """A real engine session on injected clocks. ``jumps`` maps a cycle to the
    (wall, mono, boot) seconds added in its middle."""
    monkeypatch.setattr(watch, "ThreadPoolExecutor", SyncPool)
    clock = {"t": 1_791_500_000.0, "m": 1000.0, "b": 5000.0}
    n = {"c": 0}

    def sleep(s):
        for k in clock:
            clock[k] += s

    def fake(dst, ttl, seq, wait):
        if ttl == 1:
            n["c"] += 1
        if ttl == 2 and n["c"] in jumps:
            for k, v in zip("tmb", jumps[n["c"]]):
                clock[k] += v
        return probe.Reply(f"192.0.2.{ttl}", 5.0 * ttl, ttl == 4)
    extra = {"boot": (lambda: clock["b"]) if boot is True else boot} if boot is not None else {}
    w = watch.Watch("example.net", watch.WatchOptions(max_cycles=cycles), probe_fn=fake,
                    resolve=lambda _t: "192.0.2.4", wall=lambda: clock["t"], mono=lambda: clock["m"],
                    sleep=sleep, **extra)
    return w.run()


def _broken():
    raise OSError(22, "Invalid argument")


# ------------------------------------------------------------------ wording --

@pytest.mark.parametrize("seconds,shown", [(5.0, "+5 s"), (-30.0, "-30 s"), (3600.0, "+3600 s"), (1.0, "+1 s")])
def test_a_clock_step_reads_as_one_plain_sentence(seconds, shown):
    at = 1_791_500_520.0
    when = time.strftime("%H:%M:%S", time.localtime(at))
    assert live.describe_clock_step({"at": at, "seconds": seconds}) == \
        f"Clock changed at {when} ({shown}); this cycle was kept."


def test_the_fallback_reads_as_one_plain_sentence():
    assert live.describe_clock_fallback(watch.NO_SUSPEND_CLOCK) == (
        "Clock check off: no clock on this computer counts through suspend, "
        "so a change of the system clock may show as a gap.")


# ------------------------------------------------- snapshot, table, export --

def test_a_kept_step_is_in_the_snapshot_the_table_and_the_export(monkeypatch):
    s = _session(monkeypatch, jumps={10: (5, 0, 0), 25: (-30, 0, 0)})
    assert s.gaps == [] and s.cycles == 40
    snap = live.snapshot(s)
    assert [round(c["seconds"]) for c in snap["clock_steps"]] == [5, -30] and snap["clock_fallback"] is None
    table = live.table_text(snap)
    assert "Clock changes (cycles kept): 2." in table and "Gaps" not in table and "Clock check off" not in table
    from routemap_engine import geo
    from routemap_engine.model import analyse_sync
    route = analyse_sync(watch.as_hops(s), (14.6, 121.0), sources=geo.OFFLINE).to_dict()
    body = live.route_for_export(imported.route(route), snap)
    doc = json.loads(service.export_json(body, target="example.net", trace_text="", argv=["icmp", "watch"],
                                         source="watch", origin_how="city", session=s.to_dict()))
    assert doc["format_version"] == 5
    assert [c["seconds"] for c in doc["session"]["clock_steps"]] == [5.0, -30.0]
    assert doc["session"]["clock_fallback"] is None
    # Reopened, the steps come back with their times, ready for the note and the PDF.
    back = imported.export(imported.parse_json(json.dumps(doc)))
    saved = live.saved_snapshot(back["session"])
    assert [round(c["seconds"]) for c in saved["clock_steps"]] == [5, -30]
    assert [c["at"] for c in saved["clock_steps"]] == pytest.approx([c["at"] for c in s.clock_steps], abs=1)


@pytest.mark.parametrize("boot,reason", [
    (_broken, "the clock that counts through suspend could not be read (OSError 22)"),
], ids=["read-fails"])
def test_a_fallback_is_in_the_snapshot_the_table_and_the_export(monkeypatch, boot, reason):
    s = _session(monkeypatch, jumps={10: (5, 0, 0)}, boot=boot)
    assert s.clock_fallback == reason and len(s.gaps) == 1       # the old rule: the step is a gap
    snap = live.snapshot(s)
    assert snap["clock_fallback"] == reason and snap["clock_steps"] == []
    assert live.describe_clock_fallback(reason) in live.table_text(snap)
    back = imported.session(s.to_dict())
    assert back["clock_fallback"] == reason and live.saved_snapshot(back)["clock_fallback"] == reason


def test_an_export_from_before_engine_0_8_2_opens_without_clock_notes(monkeypatch):
    s = _session(monkeypatch, jumps={})
    old = s.to_dict()
    old.pop("clock_steps")
    old.pop("clock_fallback")
    back = imported.session(old)
    assert back["clock_steps"] == [] and back["clock_fallback"] is None
    snap = live.saved_snapshot(back)
    table = live.table_text(snap)
    assert "Clock" not in table


def test_hostile_clock_values_never_survive(monkeypatch):
    s = _session(monkeypatch, jumps={}).to_dict()
    good = {"at": "2026-10-29T06:02:07Z", "seconds": 5.0}
    s["clock_steps"] = [good, {"at": "not a time", "seconds": 1}, {"at": good["at"], "seconds": "5"},
                        {"at": good["at"], "seconds": float("nan")}, {"at": good["at"], "seconds": 10**9}, "x",
                        None] + [good] * (imported.SESSION_CLOCK_STEPS + 50)
    s["clock_fallback"] = "\x1b[31mred\x07 " + "y" * 500
    back = imported.session(s)
    assert len(back["clock_steps"]) == imported.SESSION_CLOCK_STEPS - 6
    assert all(c == good for c in back["clock_steps"])
    fb = back["clock_fallback"]
    assert len(fb) <= 200 and "\x1b" not in fb and "\x07" not in fb
    s["clock_fallback"] = {"not": "text"}
    s["clock_steps"] = "nope"
    back = imported.session(s)
    assert back["clock_fallback"] is None and back["clock_steps"] == []


# ------------------------------------------------------------- the plot --

def test_markers_sit_on_the_plots_clock_when_the_session_gives_it(monkeypatch):
    """The live plot runs on the suspend-inclusive clock (engine 0.8.2), so a
    gap and a path change are placed by their own plot times, not by wall
    times that a clock change moved. A saved session has only wall times."""
    started = 1_791_500_000.0
    assert live.gap_span({"from": started + 400, "to": started + 500, "t_from": 100.0, "t_to": 160.0},
                         started) == (100.0, 160.0)
    assert live.gap_span({"from": started + 400, "to": started + 500}, started) == (400.0, 500.0)
    assert live.gap_span({"from": None, "to": 1}, started) is None
    assert live.change_t({"at": started + 400, "t": 90.0}, started) == 90.0
    assert live.change_t({"at": started + 400}, started) == 400.0
    assert live.change_t({"at": None}, started) is None
    # And a live session really gives them: a forward step leaves the plot time alone.
    s = _session(monkeypatch, jumps={10: (300, 0, 0), 20: (600, 0, 600)}, cycles=40)
    snap = live.snapshot(s)
    (gap,) = snap["gaps"]
    a, b = live.gap_span(gap, snap["started"])
    assert 600 <= b - a <= 602 and a < 25                     # the suspend, not the 300 s step
    times = [t for t, _ in snap["live"][1]]
    assert max(t2 - t1 for t1, t2 in zip(times, times[1:])) < 605


# ------------------------------------------------------------- the CLI --

@pytest.fixture
def network(monkeypatch):
    def fake_probe(dst, ttl, seq, wait):
        if ttl > 4:
            return probe.Reply(None, None)
        return probe.Reply(f"192.0.2.{ttl}", 3.0 * ttl, ttl == 4)
    monkeypatch.setattr(probe, "_probe", fake_probe)
    monkeypatch.setattr(probe, "available", lambda family=4: (True, ""))
    monkeypatch.setattr(probe, "resolve", lambda target, family="auto": "192.0.2.4")
    monkeypatch.setattr(watch, "INTERVAL_MIN", 0.01)


@pytest.mark.parametrize("platform_clock,reason", [
    (lambda: _broken, "the clock that counts through suspend could not be read (OSError 22)"),
    (lambda: None, watch.NO_SUSPEND_CLOCK),
], ids=["read-fails", "no-clock"])
def test_the_cli_says_once_when_the_clock_check_is_off(network, monkeypatch, capsys, platform_clock, reason):
    monkeypatch.setattr(watch, "suspend_clock", platform_clock)
    code = cli.main(["--watch", "example.net", "--count", "3", "--interval", "0.02", "--json", "--offline"])
    out, err = capsys.readouterr()
    assert code == 0
    assert json.loads(out)["session"]["clock_fallback"] == reason
    assert err.count(live.describe_clock_fallback(reason)) == 1


def test_only_the_fallback_record_is_kept_off_the_cli(network, monkeypatch, caplog):
    """The CLI shows the engine's clock fallback as a table note, so only that
    one log record is held back (by a filter on the engine's watch logger,
    which acts before any handler, Python's last-resort one included); any
    other record from the same logger, now or in a later engine, gets through."""
    log = logging.getLogger("routemap_engine.watch")
    real_watch = watch.Watch

    def noisy(*a, **k):
        log.warning("Watch: something else entirely")
        return real_watch(*a, **k)
    monkeypatch.setattr(watch, "suspend_clock", lambda: None)
    monkeypatch.setattr(watch, "Watch", noisy)
    with caplog.at_level("WARNING", logger="routemap_engine.watch"):
        for _ in range(2):                                # the filter is added once, however often
            assert cli.main(["--watch", "example.net", "--count", "2", "--interval", "0.02", "--offline"]) == 0
    got = [r.getMessage() for r in caplog.records if r.name == "routemap_engine.watch"]
    assert got == ["Watch: something else entirely"] * 2
    assert log.filters.count(cli._FALLBACK_SHOWN_IN_TABLE) == 1
    # The engine still logs it, in exactly the words the filter matches.
    assert any(r.msg == cli._FallbackShownInTable.MESSAGE for r in _engine_records(monkeypatch))


def _engine_records(monkeypatch):
    """What the engine logs on a fallback, with no filter in the way."""
    log = logging.getLogger("routemap_engine.watch")
    monkeypatch.setattr(log, "filters", [])
    seen = []
    handler = logging.Handler()
    handler.emit = seen.append
    log.addHandler(handler)
    try:
        _session(monkeypatch, jumps={}, boot=_broken, cycles=2)
    finally:
        log.removeHandler(handler)
    return seen


def test_the_cli_says_nothing_about_the_clock_when_it_works(network, capsys):
    assert cli.main(["--watch", "example.net", "--count", "3", "--interval", "0.02", "--json", "--offline"]) == 0
    out, err = capsys.readouterr()
    assert json.loads(out)["session"]["clock_fallback"] is None and "Clock" not in err


# ---------------------------------------------------- the window and the PDF --

@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _notes_snap():
    at = 1_791_500_520.0
    return {"changes": [], "gaps": [{"from": at - 900, "to": at - 300}],
            "clock_steps": [{"at": at + i, "seconds": 5.0} for i in range(5)],
            "clock_fallback": watch.NO_SUSPEND_CLOCK}


def test_the_live_note_lists_clock_changes_like_gaps(app):
    from routemap.gui.livepanel import ChangeList
    notes = ChangeList()
    snap = _notes_snap()
    notes.set_data(snap)
    text = notes.text()
    assert text.count("this cycle was kept.") == 3                # the last three, like gaps
    assert live.describe_clock_step(snap["clock_steps"][-1]) in text
    assert "the computer slept" in text and live.describe_clock_fallback(watch.NO_SUSPEND_CLOCK) in text
    notes.set_data({"changes": [], "gaps": []})
    assert "Clock" not in notes.text()


def test_the_pdf_has_a_line_per_clock_change_and_the_fallback(app, monkeypatch):
    from routemap.gui import report
    s = _session(monkeypatch, jumps={10: (5, 0, 0), 25: (-30, 0, 0)}).to_dict()
    s["clock_fallback"] = watch.NO_SUSPEND_CLOCK          # both at once, so one render covers both
    s["samples"]["hops"] = {}                              # no plots: only the text is checked

    class Flow:
        width, dpi = 1000, 300

        def __init__(self):
            self.lines, self.rows = [], []

        def heading(self, *a, **k):
            pass

        def table(self, header, rows, *a, **k):
            self.rows += rows

        def text(self, line, *a, **k):
            self.lines.append(line)

        def image(self, *a, **k):
            pass
    flow = Flow()
    report._session_section(flow, {"hops": []}, s)
    assert ["Clock changes", "2 (cycles kept)"] in flow.rows and ["Clock check", "off (see below)"] in flow.rows
    steps = [line for line in flow.lines if line.startswith("Clock changed at ")]
    assert len(steps) == 2 and steps[0].endswith("(+5 s); this cycle was kept.") and "(-30 s)" in steps[1]
    assert live.describe_clock_fallback(watch.NO_SUSPEND_CLOCK) in flow.lines
    flow = Flow()
    s.pop("clock_steps")
    s.pop("clock_fallback")
    report._session_section(flow, {"hops": []}, s)
    assert not any(r[0].startswith("Clock") for r in flow.rows)
    assert not any(line.startswith("Clock") for line in flow.lines)
