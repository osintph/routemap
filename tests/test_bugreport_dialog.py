"""The bug report dialog shows exactly the bytes the zip will hold."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from routemap import bugreport, config  # noqa: E402
from routemap.gui import dialogs  # noqa: E402

CURRENT = {"target": "example.net", "trace_text": "t\n", "route": {"origin": {}, "hops": []}}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _d(current=CURRENT):
    s = config.Settings()
    s.atlas_key = "11111111-2222-3333-4444-555555555555"
    return dialogs.BugReportDialog(None, build=lambda inc: bugreport.contents(s, current, inc),
                                   has_trace=bool(current), trace_label="example.net")


def test_every_file_is_listed_and_shown_verbatim(app):
    d = _d()
    assert d.files.count() == len(d.contents) == 2
    for row, (_, data) in enumerate(d.contents):
        d.files.setCurrentRow(row)
        assert d.view.toPlainText() == data.decode()
    assert "11111111-2222" not in "".join(data.decode() for _, data in d.contents)


def test_ticking_adds_the_trace_and_unticking_removes_it(app):
    d = _d()
    d.include.setChecked(True)
    assert [n for n, _ in d.contents][-1] == bugreport.TRACE and d.files.count() == 3
    d.include.setChecked(False)
    assert bugreport.TRACE not in dict(d.contents)


def test_no_trace_on_screen_cannot_be_included(app):
    d = _d(current=None)
    assert not d.include.isEnabled()


def test_the_saved_zip_is_what_was_shown(app, tmp_path):
    import zipfile
    d = _d()
    d.include.setChecked(True)
    bugreport.write_zip(tmp_path / "r.zip", d.contents)
    with zipfile.ZipFile(tmp_path / "r.zip") as z:
        assert [(i.filename, z.read(i)) for i in z.infolist()] == d.contents
