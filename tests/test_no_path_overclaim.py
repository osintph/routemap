"""Paths finds *at least* the paths a balancer offers (D4): some balancers do
not spread every kind of probe, so a path can stay hidden. No user-facing text
may claim every path or all paths, and static text never shows a literal "N"
in place of a count. Sweeps the docs, the site, the README, the privacy
notice, the app's code (UI strings, help, docstrings) and the newest
CHANGELOG entry."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERCLAIM = re.compile(r"every\s+path|all\s+paths|every\s+route\b[^.]{0,80}load\s+balancer"
                       r"|\bat\s+least\s+N\b", re.I)


def _newest_changelog_entry() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    heads = [m.start() for m in re.finditer(r"^## \[", text, re.M)]
    return text[heads[0]:heads[1]]


def _sources():
    for pattern in ("docs/*.md", "site/content/**/*.html", "routemap/**/*.py"):
        for path in sorted(ROOT.glob(pattern)):
            yield str(path.relative_to(ROOT)), path.read_text(encoding="utf-8")
    for name in ("README.md", "PRIVACY.md"):
        yield name, (ROOT / name).read_text(encoding="utf-8")
    yield "CHANGELOG.md (newest entry)", _newest_changelog_entry()


def overclaims(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text)
    return [m.group(0) for m in OVERCLAIM.finditer(flat)]


def test_no_text_claims_every_path():
    found = {name: hits for name, text in _sources() if (hits := overclaims(text))}
    assert not found, found


def test_the_guard_catches_the_wordings_it_replaced():
    for old in ("Find All Paths", "every path a load balancer offers",
                "finds every route a load balancer can send your packets along",
                "at least N paths"):
        assert overclaims(old), old
    for fine in ("Find Paths", "Paths: at least 3 paths", "Every route starts here.",
                 "every router that answers a hop is listed"):
        assert not overclaims(fine), fine
