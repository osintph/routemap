# routemap: working rules

routemap is the Route Map engine (traceroute parsing, hostname-first
geolocation, the RTT physics bound, hop annotations) plus a native PySide6
desktop app and CLI built on it. FalconEye (`~/code/falconeye`) depends on the
engine as a pinned package. Licence AGPL-3.0.

## Standing rules

- **No em dashes anywhere**: code, comments, docs, commit messages, UI
  strings, PDF output, release notes. Use a colon, a comma, parentheses or
  two sentences. `tests/test_no_em_dashes.py` enforces it for the tree.
- **vi, not nano**, whenever an editor is named in docs or instructions.
- **Programmatic writes use a heredoc or tee**, never `echo` chains or
  interactive editors: `cat > file <<'EOF'` or `... | sudo tee file`.
- **Surgical, reversible commands.** Change the one thing, say how to undo
  it, look at a target before overwriting or deleting it. No blanket
  `rm -rf`, no `git push --force`, no `git reset --hard` on a tree with work
  in it.
- **Run `TZ='Asia/Manila' date` before any time reference** (CHANGELOG
  dates, "today", release notes). Never guess the date.
- **One consolidated report per step** of a brief: what was done, what was
  verified and how, what was not verified, anything that needs Sigmund.
- **Do not stop mid-brief for clarification.** Make the reasonable call,
  record it in the report. Stop only at the points the brief names.

## The name lives in one place

The working name may change before the first release. Every runtime string
that names the product (distribution name, executable, window title, User-Agent,
config directory, repository URL) comes from `routemap/__about__.py`. The
handful of build-time literals that cannot import it are listed in
`docs/renaming.md`; a rename touches exactly those.

## Layout

- `routemap/engine/`: pure Python. **No Qt imports**, ever; a test enforces
  it. FalconEye imports this package, so anything here ships to a web server.
- `routemap/engine/data/`: bundled site-code table and GeoNames city list
  (and, from the GUI step, the Natural Earth geometry).
- `routemap/gui/`: PySide6. Thin: it calls the engine and draws.
- `routemap/cli.py`: thin, same rule.
- `tests/`: pytest. `tests/fixtures/routemap/` holds the real traces.

## Engine rules (carried over from FalconEye, where they were learned)

- The engine has **no global mutable state**. Configuration (User-Agent,
  cache, budgets, which sources are on) is passed in. Read-only bundled tables
  may be loaded lazily and kept.
- **Nothing leaves the machine that does not have to.** Only a hostname that
  passes `parse.is_routable_hostname` is sent to Hoiho; only a public address
  is sent to the IP database or the resolver; a private, CGNAT or reserved hop
  is never looked up anywhere.
- **User-supplied values in log lines go through `logsafe.tag()`.** A trace
  describes the user's own path and the origin says where they are; neither
  belongs in a log in the clear. A test sweeps the engine for it.
- **Every external source runs under a hard budget** and contributes nothing
  when it runs out. Losing a source never fails a trace.
- **Regression tests generalise over the class of bug, not the instance**, and
  are shown to fail against the pre-fix code before they count as done.

## Local environment

- Python 3.11+. Dev venv: `python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'`.
- Tests: `.venv/bin/python -m pytest -q`.
- FalconEye's own suite runs with `~/code/falconeye/.venv312` (see that
  repo's deploy runbook); FalconEye's VPS deploy is `scripts/upgrade.sh <tag>`.

## Commits and releases

- Commit identity `osintph <sb@osintph.info>`. Linear history, no merge
  commits. Annotated tags `vX.Y.Z`.
- CHANGELOG is Keep a Changelog, `## [x.y.z] - YYYY-MM-DD`, ASCII hyphen.
- Release titles are the commit subject verbatim.
