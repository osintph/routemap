"""The notices that every build must carry are present and complete."""
from routemap.gui import legal


def test_the_bundled_notices_name_the_copyleft_components_and_carry_their_texts():
    text = legal.notices_markdown()
    for needle in ("routemap-engine", "AGPL-3.0", "LGPL-3.0", "PySide6", "GeoNames",
                   "Natural Earth", "GNU LESSER GENERAL PUBLIC LICENSE",
                   "GNU AFFERO GENERAL PUBLIC LICENSE", "Mozilla Public License"):
        assert needle in text, needle


def test_the_bundled_copy_matches_the_repository_notices():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    bundled = root / "routemap" / "gui" / "data" / "legal" / "THIRD_PARTY_NOTICES.md"
    assert bundled.read_text() == (root / "THIRD_PARTY_NOTICES.md").read_text(), (
        "copy THIRD_PARTY_NOTICES.md into routemap/gui/data/legal/")
