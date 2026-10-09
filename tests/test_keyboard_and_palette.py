"""Keyboard navigation of the map and the table, the spoken row, and the RTT palettes."""
import json
import pathlib

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from routemap import config  # noqa: E402
from routemap.gui import hoptable, mapview, theme  # noqa: E402

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "gui"
ROUTE = json.loads((FIX / "heise_route.json").read_text())["route"]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("selected,delta,absolute,expected", [
    (set(), 1, False, 0), (set(), -1, False, 2), ({1}, 1, False, 1), ({4}, 1, False, 2),
    ({4}, -1, False, 0), ({1}, -1, False, 0), ({4, 5}, 1, False, 2), (set(), 0, True, 0), ({1}, -1, True, 2),
])
def test_step_index(selected, delta, absolute, expected):
    groups = [[1], [2, 3], [4, 5]]
    if selected == {4}:
        groups = [[1], [4], [6]]
    assert mapview.step_index(groups, selected, delta, absolute) == expected


def test_no_groups_selects_nothing():
    assert mapview.step_index([], set(), 1) is None


def _window():
    from routemap.gui.mainwindow import MainWindow
    w = MainWindow()
    w.resize(1440, 900)
    w.show()
    w.show_result(ROUTE, "heise.de", ["icmp", "heise.de"])
    w.table.set_hops(ROUTE["hops"], {})
    return w


def test_arrow_keys_walk_the_map_and_the_table_follows(app):
    w = _window()
    view = w.map.flat
    view.setFocus()
    QTest.keyClick(view, Qt.Key_Home)
    first = sorted(view.selected_hops)
    QTest.keyClick(view, Qt.Key_Right)
    second = sorted(view.selected_hops)
    assert first and second and min(second) > min(first)
    assert view.accessibleDescription().startswith(("Hop ", "Hops "))
    selected_rows = {w.table.model_.hops[i.row()]["hop"] for i in w.table.selectionModel().selectedRows()}
    assert selected_rows and selected_rows <= set(second)
    assert view.hasFocus() or not w.isActiveWindow()   # focus stays on the map
    QTest.keyClick(view, Qt.Key_End)
    markers = view.ordered_markers()
    assert set(view.selected_hops) == set(markers[-1].hops)
    QTest.keyClick(view, Qt.Key_Escape)
    assert not view.selected_hops
    w.close()


def test_shift_arrows_still_move_the_view(app, monkeypatch):
    w = _window()
    view = w.map.flat
    moves = []
    monkeypatch.setattr(view, "pan", lambda dx, dy: moves.append((dx, dy)))
    for key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
        QTest.keyClick(view, key, Qt.ShiftModifier)
    assert len(moves) == 4 and not view.selected_hops
    w.close()


def test_the_globe_walks_the_same_hops(app):
    w = _window()
    w.map.set_projection("globe")
    globe = w.map.globe
    QTest.keyClick(globe, Qt.Key_Home)
    QTest.keyClick(globe, Qt.Key_Right)
    assert globe.selected_hops and globe.accessibleDescription()
    w.close()


def test_a_row_is_spoken_in_full(app):
    m = hoptable.HopModel()
    m.set_hops(ROUTE["hops"], {})
    limited = next(i for i, h in enumerate(m.hops) if hoptable.rate_limited(h))
    spoken = m.data(m.index(limited, 0), Qt.AccessibleTextRole)
    assert spoken.startswith(f"Hop {m.hops[limited]['hop']}") and "ICMP rate limiting, not real loss" in spoken
    assert m.data(m.index(limited, hoptable.KEYS.index("loss")), Qt.AccessibleTextRole).startswith("Loss: ")


def test_colour_blind_palette_swaps_warm_and_hot_and_dashes_hot():
    for base in (theme.LIGHT, theme.DARK):
        std = theme.with_rtt(base, "standard")
        cb = theme.with_rtt(base, "colour-blind")
        assert std is base and not std.hot_dashed
        warm, hot = theme.COLOUR_BLIND[base.dark]
        assert (cb.route_warm.name(), cb.route_hot.name()) == (warm, hot) and cb.hot_dashed
        assert cb.route_quiet == base.route_quiet


def test_the_choice_is_saved_and_unknown_values_fall_back():
    s = config.Settings()
    s.rtt_palette = "colour-blind"
    config.save_settings(s)
    assert config.load_settings().rtt_palette == "colour-blind"
    s.rtt_palette = "neon"
    config.save_settings(s)
    assert config.load_settings().rtt_palette == "standard"


def test_exports_use_the_chosen_palette(app):
    def render(name):
        theme.set_rtt_palette(name)
        try:
            return mapview.render_png(ROUTE, width=600, height=338, title="", provenance="")
        finally:
            theme.set_rtt_palette("standard")

    std, cb = render("standard"), render("colour-blind")
    assert std.size() == cb.size() and std != cb
