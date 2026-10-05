"""nginx configs in the repository: the rule that refuses hidden paths comes
before every other regex location (nginx tries regex locations in file order,
so a hidden ".env.txt" or ".git/README.md" was served by an earlier
"\\.(txt|asc|md)$" rule; RM-17)."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def regex_locations(text: str) -> list[str]:
    return re.findall(r"^\s*location\s+~\*?\s+(\S+)", text, flags=re.M)


def test_hidden_paths_are_refused_before_any_other_regex_location():
    confs = sorted(ROOT.glob("docs/**/*.conf"))
    checked = 0
    for conf in confs:
        text = conf.read_text(encoding="utf-8")
        locs = regex_locations(text)
        if not locs:
            continue
        checked += 1
        assert locs[0].startswith("/\\."), f"{conf.name}: first regex location is {locs[0]}, not the hidden-path deny"
        block = text[text.index(locs[0]):].split("}", 1)[0]
        assert "deny all" in block or "return 404" in block, f"{conf.name}: the first regex location does not refuse"
    assert checked, "no nginx config with regex locations found"
