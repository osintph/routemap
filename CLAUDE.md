# routemap: working rules

This PUBLIC repository is the Route Map desktop app (PySide6 GUI, CLI, exports,
packaging, CI), free software under the GNU AGPL-3.0. The engine is the
separate public AGPL-3.0 package routemap-engine
(github.com/osintph/routemap-engine, import `routemap_engine`), which FalconEye
(`~/code/falconeye`) also depends on. Releases are on GitHub Releases with GPG
signed `SHA256SUMS`; an optional pre-release site with per-tester logins is
described in docs/download-host/. Contributions need the CLA (CLA.md).

Nothing about any separate commercial product goes into this repository or its
history. Briefs, screenshots for review, review pages, tester data, keys and
host details (addresses, ports, paths of other sites) never go into git: review
pages are private claude.ai artifacts, host notes live in ~/.routemap-testers/.
The local branch `pro-seed` is private and never pushed (a local pre-push hook
refuses it).

- Never copy secrets or host details into either repository.
- Engine changes are made in the engine repo and released there; this repo then
  moves its pin.
- Keep test matrices lean and builds on tags or manual dispatch only.

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

- `routemap/gui/`: PySide6. Thin: it calls the engine and draws.
- `routemap/gui/data/`: Natural Earth map, icon, sample trace, legal texts.
- `routemap/config.py`, `routemap/service.py`: settings and engine wiring, Qt-free.
- `packaging/`: Nuitka build, source-leak and Windows verifiers, release notes.
- `routemap/cli.py`: thin, same rule.
- `tests/`: pytest. `tests/fixtures/routemap/` holds the real traces.

## Engine rules (apply in routemap-engine; the app must respect them too)

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
