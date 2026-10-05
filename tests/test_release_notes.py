"""Release notes are published as GitHub Markdown, where a single line break
inside a paragraph shows as a real break. Every paragraph and list item of
the notes is one line (4d), for every version in the changelog, and no word
is lost or added on the way."""
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))
import release_notes  # noqa: E402

VERSIONS = re.findall(r"^## \[([^\]]+)\]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
STARTS = re.compile(r"^(\s*([-*+]|\d+\.)\s|#{1,6}\s|---\s*$|```|\|)")


def _continuations(text: str) -> list[str]:
    bad, previous, fenced = [], "", False
    for line in text.split("\n"):
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.strip() and previous.strip() and not STARTS.match(line):
            bad.append(line[:70])
        previous = "" if fenced else line
    return bad


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("signed", [False, True], ids=["unsigned", "signed"])
def test_every_paragraph_and_list_item_is_one_line(version, signed):
    text = release_notes.notes(f"v{version}", "D57C7E26C19F9436E2D66F37408097D191DDF981", signed)
    assert not _continuations(text), _continuations(text)[:5]


def test_joining_keeps_every_word():
    raw = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    section = re.search(r"^## \[0\.2\.0-beta\.3\].*?$(.*?)(?=^## \[)", raw, re.M | re.S).group(1)
    assert release_notes.unwrap(section).split() == section.split()
