"""Continuous mode in the window, end to end, against a scripted network.

The engine's probe and resolver are replaced and the interval floor lowered
so a session runs in a fraction of a second; everything else is the real
window, controller, placement (offline), history, export and import.
"""
import json
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from routemap_engine import probe, watch  # noqa: E402

from routemap import config, imported  # noqa: E402

DEPTH = 6


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def network(monkeypatch):
    state = {"cycle": 0}

    def fake_probe(dst, ttl, seq, wait):
        if ttl == 1:
            state["cycle"] += 1
        if ttl > DEPTH:
            return probe.Reply(None, None)
        if ttl == 3 and state["cycle"] % 3 == 0:
            return probe.Reply(None, None)          # rate limiting at hop 3
        return probe.Reply(f"192.0.2.{ttl}", 5.0 * ttl, ttl == DEPTH)

    monkeypatch.setattr(probe, "_probe", fake_probe)
    monkeypatch.setattr(probe, "available", lambda: (True, ""))
    monkeypatch.setattr(watch.socket, "gethostbyname", lambda host: "192.0.2.6")
    monkeypatch.setattr(watch, "INTERVAL_MIN", 0.01)
    return state


def _controller():
    from routemap.gui.app import Controller
    from routemap.gui.mainwindow import MainWindow
    s = config.Settings()
    s.online_lookups = False             # placement from the offline data only
    s.live_interval = 0.02
    w = MainWindow()
    w.resize(1440, 900)
    w.show()
    c = Controller(w, s)
    return w, c


def _wait(app, until, seconds=20.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if until():
            return True
        QTest.qWait(10)
    return False


def test_a_session_runs_shows_pauses_stops_and_is_kept(app, network, tmp_path):
    w, c = _controller()
    w.target.setText("example.net")
    c.watch()
    assert _wait(app, lambda: c.live_snap and c.live_snap["cycles"] >= 15)
    assert w.table.model_.columns[2] == "Loss" and w.live_bar.isVisible() and w.live_plot.isVisible()
    assert _wait(app, lambda: c.live_route is not None)                # placed once, offline
    hops = {h["hop"]: h for h in w.table.model_.hops}
    assert set(hops) == set(range(1, DEPTH + 1))
    assert "ICMP rate limiting, not real loss" in hops[3]["annotations"]
    assert hops[DEPTH]["loss_pct"] == 0.0

    # P in the target field types a letter; P on the table pauses.
    w.target.setFocus()
    QTest.keyClick(w.target, Qt.Key_P)
    assert not c.watcher.paused and w.target.text().endswith("p")
    w.table.setFocus()
    QTest.keyClick(w.table, Qt.Key_P)
    assert c.watcher.paused and w.live_bar.pause.text() == "Resume"
    paused_at = c.live_snap["cycles"]
    QTest.qWait(200)
    app.processEvents()
    assert c.live_snap["cycles"] == paused_at
    QTest.keyClick(w.table, Qt.Key_P)
    assert not c.watcher.paused
    assert _wait(app, lambda: c.live_snap["cycles"] > paused_at)

    c.stop()
    assert _wait(app, lambda: not c.watching() and c.current and c.current.get("session"))
    assert c.current["source"] == "watch" and w.live_bar.export.isVisible()
    entry = config.load_history()[0]
    assert entry["source"] == "watch" and entry["session"]["cycles"] == c.current["session"]["cycles"]

    # Export and open again: format 3, the session survives the rebuild.
    from routemap.gui.app import write_export
    path = tmp_path / "s.json"
    write_export("json", str(path), c.current, settings=c.settings)
    doc = json.loads(path.read_text())
    assert doc["format_version"] == 3 and doc["session"]["cycles"] >= 15
    back = imported.export(imported.parse_json(path.read_text()))
    assert back["session"]["cycles"] == doc["session"]["cycles"]
    assert [h["hop"] for h in back["session"]["hops"]] == list(range(1, DEPTH + 1))
    pdf = tmp_path / "s.pdf"
    write_export("pdf", str(pdf), c.current, settings=c.settings)
    assert pdf.stat().st_size > 10_000
    w.close()


def test_a_stored_session_reopens_stopped(app, network):
    w, c = _controller()
    w.target.setText("example.net")
    c.watch()
    assert _wait(app, lambda: c.live_snap and c.live_snap["cycles"] >= 5)
    c.stop()
    assert _wait(app, lambda: not c.watching() and c.current and c.current.get("session"))
    c.refresh_history()
    c.leave_live()
    c.open_history(0)
    assert w.live_bar.export.isVisible() and not w.live_bar.pause.isVisible()
    assert w.table.model_.columns[2] == "Loss"
    assert w.live_plot.snap and w.live_plot.snap["live"]
    w.close()


def test_a_normal_trace_leaves_live_mode(app, network):
    w, c = _controller()
    w.target.setText("example.net")
    c.watch()
    assert _wait(app, lambda: c.live_snap and c.live_snap["cycles"] >= 3)
    c.stop()
    assert _wait(app, lambda: not c.watching())
    c.leave_live()
    assert w.table.model_.columns[2] == "Source" and not w.live_bar.isVisible()
    w.close()


def test_ipv6_target_says_why(app, network, monkeypatch):
    monkeypatch.setattr(watch.socket, "gethostbyname", lambda host: "2001:db8::1")
    errors = []
    w, c = _controller()
    monkeypatch.setattr(c, "error", lambda title, text: errors.append(text))
    w.target.setText("example.net")
    c.watch()
    assert _wait(app, lambda: errors)
    assert "IPv4" in errors[0]
    w.close()


def _snap(changes=(), paused=False):
    pts = [(float(t), None if t % 17 == 0 else 20.0 + (t % 5)) for t in range(120)]
    return {"target": "x", "cycles": 120, "started": 1_791_500_000.0, "now": 1_791_500_120.0,
            "interval": 1.0, "duration": 3600.0, "reached_hop": 6, "paused": paused,
            "hops": [{"hop": n} for n in range(1, 7)], "loss": {"text": ""}, "stopped_by": None,
            "changes": list(changes), "gaps": [], "live": {n: pts for n in range(1, 7)}}


def test_live_mode_names_every_control(app, network):
    from tests.test_accessible_names import unnamed
    w, c = _controller()
    w.target.setText("example.net")
    c.watch()
    assert _wait(app, lambda: c.live_snap and c.live_snap["cycles"] >= 3)
    missing = unnamed(w)
    c.stop()
    _wait(app, lambda: not c.watching())
    w.close()
    assert not missing, missing


def test_the_bar_announces_state_changes_not_every_tick(app):
    from routemap.gui.livepanel import LiveBar
    bar = LiveBar()
    bar.show_state(_snap(), running=True)
    first = bar.state.accessibleName()
    bar.show_state(dict(_snap(), cycles=121), running=True)
    assert bar.state.accessibleName() == first == "Continuous trace running"
    bar.show_state(_snap(paused=True), running=True)
    assert bar.state.accessibleName() == "Continuous trace paused"
    bar.show_state(dict(_snap(), stopped_by="duration"), running=False)
    assert "reached its time limit" in bar.state.accessibleName()


def test_a_path_change_is_announced(app):
    from routemap.gui.livepanel import ChangeList
    cl = ChangeList()
    cl.set_data(_snap())
    cl.set_data(_snap([{"cycle": 30, "at": 1_791_500_030.0, "hop": 4, "kind": "address",
                        "old": ["192.0.2.4"], "new": ["198.51.100.4"]}]))
    assert cl.accessibleName().startswith("Path change. Cycle 30:")


def test_the_plot_uses_the_chosen_palette_and_describes_itself(app):
    from routemap.gui import theme
    from routemap.gui.livepanel import PingPlot
    images = []
    for name in ("standard", "colour-blind"):
        theme.set_rtt_palette(name)
        try:
            plot = PingPlot()
            plot.resize(600, 170)
            plot.set_data(_snap(), 3)
            images.append(plot.grab().toImage())
        finally:
            theme.set_rtt_palette("standard")
    assert images[0] != images[1]
    plot = PingPlot()
    plot.set_data(_snap(), 3)
    assert plot.accessibleDescription().startswith("Last 5 min. Hop 3:")
    QTest.keyClick(plot, Qt.Key_4)
    assert plot.accessibleDescription().startswith("Whole session.")
