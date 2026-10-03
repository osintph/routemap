"""Release notes for the download site: install steps for unsigned builds first,
then this version's CHANGELOG section (which lists what changed).

    python packaging/release_notes.py v0.1.0-beta.2
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main(tag: str) -> int:
    version = tag.lstrip("v")
    first = (ROOT / "packaging" / "release-notes-unsigned.md").read_text(encoding="utf-8").strip()
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\].*?$(.*?)(?=^## \[|\Z)", changelog, re.M | re.S)
    body = match.group(1).strip() if match else f"Release {version}."
    print(first + "\n\n---\n\n" + body + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
