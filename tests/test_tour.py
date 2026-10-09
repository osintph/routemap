"""The first-run tour: platform menu paths, keys, and when it is shown."""
import json

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from routemap import config  # noqa: E402
from routemap.gui import tour  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("system,path,wrong", [("darwin", "Route Map › Settings", "Edit › Settings"),
                                               ("win32", "Edit › Settings", "Route Map › Settings"),
                                               ("linux", "Edit › Settings", "Route Map › Settings")])
def test_menu_paths_follow_the_platform(system, path, wrong):
    text = " ".join(s["text"] for s in tour.steps(system))
    assert path in text and wrong not in text


def test_five_cards_cover_origin_trace_map_table_and_help():
    assert [s["key"] for s in tour.steps("linux")] == ["origin", "trace", "map", "table", "help"]


def test_every_card_points_at_a_real_widget(app):
    from routemap.gui.mainwindow import MainWindow
    w = MainWindow()
    for card in tour.steps():
        attr = getattr(w, card["target"])
        assert (attr() if callable(attr) else attr) is not None, card["target"]
    w.close()


def test_keys_move_back_forward_and_escape_ends(app):
    from routemap.gui.mainwindow import MainWindow
    w = MainWindow()
    w.show()
    t = tour.Tour(w, "linux")
    ended = []
    t.finished.connect(lambda: ended.append(True))
    QTest.keyClick(t, Qt.Key_Right)
    assert t.index == 1 and t.accessibleName().startswith("Tour, step 2 of 5")
    QTest.keyClick(t, Qt.Key_Left)
    assert t.index == 0
    QTest.keyClick(t, Qt.Key_Escape)
    assert ended == [True]
    w.close()


def test_done_on_the_last_card_ends_it(app):
    from routemap.gui.mainwindow import MainWindow
    w = MainWindow()
    t = tour.Tour(w, "linux")
    ended = []
    t.finished.connect(lambda: ended.append(True))
    for _ in range(4):
        t.next.click()
    assert t.next.text() == "Done" and not t.skip.isVisible()
    t.next.click()
    assert ended == [True]
    w.close()


def test_a_fresh_install_has_not_seen_the_tour():
    assert config.load_settings().tour_seen is False


def test_settings_from_before_the_tour_count_as_seen():
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps({"theme": "dark"}))
    assert config.load_settings().tour_seen is True


def test_finishing_the_tour_is_remembered():
    s = config.Settings()
    s.tour_seen = True
    config.save_settings(s)
    assert config.load_settings().tour_seen is True
