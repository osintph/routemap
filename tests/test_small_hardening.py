"""Hardening 17: copied hop rows cannot become spreadsheet formulas, and a
refreshed site-code table is checked before it replaces anything."""
import os

import pytest


from PySide6.QtWidgets import QApplication  # noqa: E402

from routemap import cli, config  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


FORMULAS = ['=HYPERLINK("http://x","y")', "+cmd|' /C calc'!A0", "-2+3+cmd|' /C calc'!A0", "@SUM(1+1)*cmd|' /C calc'!A0",
            "\t=1+1", "\r=1+1"]


def test_copied_cells_never_start_a_formula(app):
    from routemap.gui.hoptable import HopTable
    hops = [{"hop": i + 1, "hostname": f, "address": "192.0.2.1", "addresses": ["192.0.2.1"],
             "hostnames": [f], "place": f, "lat": -33.9, "lon": -70.6, "min_rtt_ms": None,
             "avg_rtt_ms": None, "source": "hoiho", "as_org": f, "asn": 1299} for i, f in enumerate(FORMULAS)]
    table = HopTable()
    table.set_hops(hops)
    text = table.copy_selection()
    cells = [c for line in text.splitlines()[1:] for c in line.split("\t")]
    assert cells
    for cell in cells:
        if cell[:1] in ("=", "+", "-", "@"):
            assert cell == "-" or cell.lstrip("-").replace(".", "", 1).isdigit(), f"formula cell: {cell!r}"


def test_a_site_table_with_a_bad_code_replaces_nothing(tmp_path, monkeypatch):
    from routemap_engine import sitegen
    out = config.site_codes_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("# the table in use\narelion\tadm\tAmsterdam\tNL\t52.37\t4.89\tarelion-lg\n")
    before = out.read_text()

    def poisoned(argv):
        target = argv[argv.index("--out") + 1]
        with open(target, "w") as handle:
            handle.write("# generated\narelion\tadm\tAmsterdam\tNL\t52.37\t4.89\tarelion-lg\n"
                         "evil\t<img src=x>\tNowhere\tNL\t1.0\t1.0\tevil-lg\n")
        return 0
    monkeypatch.setattr(sitegen, "main", poisoned)
    assert cli.main(["sites", "update"]) != 0
    assert out.read_text() == before


def test_a_good_site_table_replaces_the_old_one(tmp_path, monkeypatch):
    from routemap_engine import sitegen
    out = config.site_codes_path()
    good = "# generated\narelion\tadm\tAmsterdam\tNL\t52.37\t4.89\tarelion-lg\n"

    def fine(argv):
        with open(argv[argv.index("--out") + 1], "w") as handle:
            handle.write(good)
        return 0
    monkeypatch.setattr(sitegen, "main", fine)
    assert cli.main(["sites", "update"]) == 0
    assert out.read_text() == good
