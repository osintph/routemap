"""The notices and licence texts bundled with every build, for Help > Third-Party Notices."""
from __future__ import annotations

from importlib import resources

LICENCE_FILES = ("LGPL-3.0.txt", "GPL-3.0.txt", "AGPL-3.0.txt", "MPL-2.0.txt", "APACHE-2.0.txt")


def notices_markdown() -> str:
    base = resources.files("routemap.gui").joinpath("data/legal")
    text = base.joinpath("THIRD_PARTY_NOTICES.md").read_text("utf-8")
    for name in LICENCE_FILES:
        try:
            body = base.joinpath(name).read_text("utf-8")
        except FileNotFoundError:
            continue
        text += f"\\n\\n---\\n\\n## {name[:-4]}\\n\\n```\\n{body}\\n```\\n"
    return text
