"""The Atlas cost has one source, the engine's TRACEROUTE_CREDITS.

Generalised over the class of bug (a figure copied into the UI or the docs and
left behind when the engine's changes): no GUI source states a credit figure
as a literal, and every figure the docs and site give is the engine's.
"""
import pathlib
import re
import subprocess

from routemap_engine.atlas import TRACEROUTE_CREDITS

ROOT = pathlib.Path(__file__).resolve().parents[1]
# A stated cost: "costs 60 credits", "costs 60 of your credits", "traceroute (60 credits".
# RIPE's own figures (income per day, the one-time grant) are not costs.
FIGURE = re.compile(r"(?:costs?\s+|traceroute\s+\()(\d+)\s+(?:of\s+your\s+)?credits\b", re.I)


def test_gui_never_states_a_credit_figure_as_a_literal():
    for path in (ROOT / "routemap").rglob("*.py"):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            assert not re.search(r"\b\d+\s+(?:of your\s+)?credits\b", line), f"{path}:{n}: {line.strip()}"


def test_docs_and_site_give_the_engines_figure():
    tracked = subprocess.run(["git", "ls-files", "docs", "site", "README.md"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
    for name in tracked:
        path = ROOT / name
        if path.suffix not in {".md", ".html"} or not path.is_file():
            continue
        for m in FIGURE.finditer(path.read_text(encoding="utf-8")):
            figure = int(m.group(1))
            assert figure == TRACEROUTE_CREDITS, f"{path}: {m.group(0)!r}"
