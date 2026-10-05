"""Exports and history files written by every released version open
unchanged with the current import rules (the number limits, coordinate pairs
and the parser of the malformed-export fixes included). The fixtures were
written by each release's own code and engine from the public fixture traces:
0.2.0-beta.1 (engine 0.3.0), beta.2 (0.4.0) and beta.3 (0.4.1)."""
import json
import pathlib

import pytest

from routemap import config, imported

ROOT = pathlib.Path(__file__).resolve().parent / "fixtures" / "old_exports"
EXPORTS = sorted(ROOT.glob("*/*.json"))
VERSIONS = sorted(p.name for p in ROOT.iterdir() if p.is_dir())


def test_every_released_version_is_covered():
    assert VERSIONS == ["0.2.0-beta.1", "0.2.0-beta.2", "0.2.0-beta.3"]


@pytest.mark.parametrize("path", EXPORTS, ids=[f"{p.parent.name}/{p.stem}" for p in EXPORTS])
def test_an_old_export_rebuilds_to_exactly_its_route(path):
    text = path.read_text(encoding="utf-8")
    original = json.loads(text)["route"]
    rebuilt = imported.export(imported.parse_json(text))
    assert rebuilt["route"] == original


@pytest.mark.parametrize("version", VERSIONS)
def test_an_old_history_file_loads_every_entry_unchanged(version):
    raw = (ROOT / version / "history.json.fixture").read_text(encoding="utf-8")
    config.history_path().parent.mkdir(parents=True, exist_ok=True)
    config.history_path().write_text(raw, encoding="utf-8")
    loaded, written = config.load_history(), json.loads(raw)
    assert len(loaded) == len(written) == 4
    for new, old in zip(loaded, written):
        assert new["route"] == old["route"]
        assert {k: new[k] for k in ("target", "when", "hops", "placed", "source")} == \
               {k: old[k] for k in ("target", "when", "hops", "placed", "source")}
