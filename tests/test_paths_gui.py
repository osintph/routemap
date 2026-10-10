"""Paths and reverse traces in the window (0.4.0): every path is drawn and
listed with its own loss and latency, a chosen path stands out, the consent
dialog says what is published, and no reverse trace runs without consent or
after it was withdrawn."""
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from routemap import config, reverse, service  # noqa: E402
from routemap_engine import multipath  # noqa: E402
from routemap_engine.geo import Sources  # noqa: E402
from routemap_engine.probe import FlowAnswer  # noqa: E402

# Ordinary public addresses: documentation ranges are never looked up, so
# they would never be placed.
PLACES = {"62.115.0.1": (14.6, 121.0), "62.115.0.2": (1.29, 103.85), "62.115.0.3": (48.86, 2.35),
          "62.115.0.4": (43.3, 5.37), "62.115.0.5": (50.11, 8.68), "62.115.0.9": (52.37, 9.73)}
DST = "62.115.0.9"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class Lab:
    """Two paths split at hop 3 (Paris or Marseille); Marseille loses a ping in two."""
    def __init__(self):
        self.t, self.queue, self.n = 1000.0, [], 0

    def clock(self):
        return self.t

    def route(self, flow):
        return ["62.115.0.1", "62.115.0.2", "62.115.0.3" if flow % 2 else "62.115.0.4", "62.115.0.5", DST]

    def send(self, flow, ttl, seq):
        r = self.route(flow)
        self.n += 1
        if ttl == multipath.PING_HOPS and flow % 2 == 0 and self.n % 2:
            return
        rtt = (0.002, 0.040, 0.200, 0.230, 0.250)[min(ttl, 5) - 1]     # what the distances allow
        self.queue.append((self.t + rtt, FlowAnswer(seq, r[min(ttl, 5) - 1], ttl >= 5, self.t + rtt)))

    def read(self, timeout):
        due = [q for q in self.queue if q[0] <= self.t + timeout]
        self.queue = [q for q in self.queue if q[0] > self.t + timeout]
        self.t = max(self.t + (0 if due else timeout), max((d[0] for d in due), default=0))
        return [a for _, a in due]

    def close(self):
        pass


@pytest.fixture
def fake_paths(monkeypatch):
    def discover(target, **kw):
        lab = Lab()
        return multipath.Discoverer(target, DST, lab, clock=lab.clock, options=kw.get("options")).run()
    monkeypatch.setattr(multipath, "discover", discover)
    monkeypatch.setattr(multipath, "available", lambda: (True, ""))

    async def ip_db(addresses):
        return {a: {"lat": PLACES[a][0], "lon": PLACES[a][1], "city": f"City{a[-1]}", "cc": "DE"}
                for a in addresses if a in PLACES}
    monkeypatch.setattr(service, "sources_for", lambda settings: Sources(hoiho=None, ip_db=ip_db, ptr=None))


def _wait(app, until, seconds=20.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if until():
            return True
        QTest.qWait(10)
    return False


def _close(app, w, c):
    """Let the last background job end before the window goes."""
    _wait(app, lambda: not c.busy(), 10)
    for task in (c.task, c.insight_task, c.detail_task, c.origin_task):
        if task is not None:
            task.wait(5000)
    app.processEvents()
    w.close()


@pytest.fixture(autouse=True)
def no_online_insight(monkeypatch):
    """The reverse tests turn Online lookups on; the window's RIPE details
    must still not reach the network."""
    from routemap import insight

    async def offline_only(route, ins, settings, **kw):
        ins["online"] = {"status": insight.OFF}
    monkeypatch.setattr(insight, "online", offline_only)


def _controller(**settings):
    from routemap.gui.app import Controller
    from routemap.gui.mainwindow import MainWindow
    s = config.Settings(online_lookups=False)
    for k, v in settings.items():
        setattr(s, k, v)
    w = MainWindow()
    w.resize(1440, 900)
    w.show()
    c = Controller(w, s)
    c.origin = (14.6, 121.0, "Manila, PH")
    return w, c


def _paths(app, w, c):
    w.target.setText("example.net")
    c.find_paths()
    assert _wait(app, lambda: c.current and c.current["route"].get("paths"))
    return c.current["route"]["paths"]


def test_every_path_is_drawn_and_listed_with_its_loss_and_latency(app, fake_paths):
    from routemap.gui import mapview
    w, c = _controller()
    disc = _paths(app, w, c)
    assert len(disc["paths"]) == 2 and c.current["source"] == "paths"
    m = w.table.model_
    assert m.columns[1] == "Paths"
    labels = [m.text(h, 0) for h in m.hops]
    assert "3a" in labels and "3b" in labels and m.text(m.hops[0], 1) == "all"
    assert w.paths.list.topLevelItemCount() == 2 and "at least 2 paths" in w.paths.toggle.text()
    rows = [[w.paths.list.topLevelItem(i).text(col) for col in range(5)] for i in range(2)]
    assert all(r[3].endswith(" ms") for r in rows)
    assert any(r[4].startswith("0%") for r in rows) and any(not r[4].startswith("0%") for r in rows)
    segs = mapview.path_segments(c.current["route"])
    assert {s["id"] for s in segs} == {"A", "B"} and sum(s["first"] for s in segs) == 2
    assert "at least 2 paths" in w.summary.text()
    _close(app, w, c)


def test_selecting_a_path_shows_it_alone_on_the_map(app, fake_paths):
    w, c = _controller()
    _paths(app, w, c)
    w.paths.expand(True)
    w.paths.list.setCurrentItem(w.paths.list.topLevelItem(1))
    assert w.map.flat.selected_path == w.paths.list.topLevelItem(1).text(0)
    assert w.map.globe.selected_path == w.map.flat.selected_path
    w.paths.list.clearSelection()
    assert w.map.flat.selected_path is None
    _close(app, w, c)


def test_the_consent_dialog_says_public_and_names_the_ip_and_the_cost(app):
    from routemap.gui import dialogs
    d = dialogs.ReverseConsentDialog(None, target="heise.de", ip="203.0.113.47")
    text = d.text()
    for words in ("RIPE Atlas measurements are public", "203.0.113.47", "cannot remove it afterwards",
                  f"{reverse.CREDITS} of your Atlas credits", reverse.AGREE, "Settings › RIPE Atlas"):
        assert words in text
    assert not d.allow.isEnabled() and d.not_now.isDefault()
    d.agree.setChecked(True)
    assert d.allow.isEnabled()


def _planned(monkeypatch, runs, consent_answer, confirm_answer=True):
    from routemap.gui import dialogs

    async def plan(route, settings, **kw):
        return reverse.Plan(af=4, public_ip="203.0.113.47", probe={"id": 6012, "asn": 12306, "country": "DE",
                                                                    "lat": 52.4, "lon": 9.7})
    monkeypatch.setattr(reverse, "plan", plan)
    monkeypatch.setattr(reverse, "run_sync", lambda *a, **kw: runs.append(kw) or {
        "measurement_id": 1, "af": 4, "trace_text": "t", "probe": {"id": 6012},
        "route": __import__("routemap_engine").analyse_sync(
            "traceroute to x (203.0.113.47), 30 hops max\n 1  203.0.113.5  1.0 ms\n 2  203.0.113.47  9.0 ms\n",
            sources=__import__("routemap_engine").OFFLINE)})
    monkeypatch.setattr(dialogs.ReverseConsentDialog, "exec", lambda self: consent_answer)
    monkeypatch.setattr(dialogs.ReverseConfirmDialog, "exec", lambda self: confirm_answer)


def test_no_reverse_trace_runs_before_consent_or_after_withdrawal(app, fake_paths, monkeypatch):
    runs = []
    w, c = _controller(atlas_enabled=True, atlas_key="k", online_lookups=True)
    _paths(app, w, c)
    assert w.reverse_button.isVisible() and w.act_reverse.isEnabled()
    _planned(monkeypatch, runs, consent_answer=False)
    c.reverse_trace()
    assert _wait(app, lambda: not c.busy() and w.trace_button.text() == "Trace", 5)   # the answer was handled
    assert runs == [] and not reverse.consented(c.settings)
    _planned(monkeypatch, runs, consent_answer=True)
    c.reverse_trace()
    assert _wait(app, lambda: c.current.get("reverse"))
    assert len(runs) == 1 and runs[0]["consent"] is True and reverse.consented(config.load_settings())
    assert w.reverse.isVisible() and w.map.flat.reverse_route is not None
    c.withdraw_reverse_consent()
    assert not reverse.consented(config.load_settings())
    _planned(monkeypatch, runs, consent_answer=False)
    c.reverse_trace()
    assert _wait(app, lambda: not c.busy() and w.trace_button.text() == "Trace", 5)   # the answer was handled
    assert len(runs) == 1
    _close(app, w, c)


def test_a_reverse_trace_joins_its_trace_in_history_and_in_the_export(app, fake_paths, monkeypatch, tmp_path):
    import json
    from routemap import imported
    from routemap.gui.app import write_export
    runs = []
    w, c = _controller(atlas_enabled=True, atlas_key="k", online_lookups=True)
    _paths(app, w, c)
    _planned(monkeypatch, runs, consent_answer=True)
    c.reverse_trace()
    assert _wait(app, lambda: c.current.get("reverse"))
    assert config.load_history()[0].get("reverse", {}).get("measurement_id") == 1
    out = tmp_path / "x.json"
    write_export("json", str(out), c.current)
    doc = imported.export(json.loads(out.read_text()))
    assert doc["reverse"]["probe"]["id"] == 6012 and doc["route"]["paths"]["paths"]
    _close(app, w, c)
