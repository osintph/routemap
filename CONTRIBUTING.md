# Contributing to Route Map

Thank you for your interest. Bug reports and ideas are welcome as
[issues](https://github.com/osintph/routemap/issues). For code, read this first.

## Before you open a pull request

- **The CLA.** Every pull request needs the [Contributor Licence Agreement](CLA.md)
  signed once by each author. A bot comments on your first pull request with
  one sentence to post; that is the signature. In short, you keep your
  copyright and give the project a licence to use your contribution under any
  terms, including outside the AGPL. This keeps the project free to relicense
  later, including in a separate commercial product. If you are not comfortable
  with that, please open an issue instead of a pull request.
- **Contributions may be declined.** The maintainer may decline any pull
  request, for any reason, including ones that are correct and useful but do
  not fit the project's direction or would be hard to maintain. For anything
  larger than a small fix, open an issue first and ask.
- **The engine lives elsewhere.** Geolocation and parsing changes belong in
  [routemap-engine](https://github.com/osintph/routemap-engine); this
  repository is the desktop app, CLI and packaging.

## How the code is kept

- Python 3.11 or later. `python3.12 -m venv .venv && .venv/bin/pip install -e '.[gui,dev]'`
- Tests: `.venv/bin/python -m pytest -q`. A change comes with a test, and a
  regression test covers the class of bug, not only the one instance.
- **No em dashes** anywhere: code, comments, docs, UI strings, commit messages.
  `tests/test_no_em_dashes.py` enforces it.
- Nothing leaves the user's machine that does not have to. A new network call
  needs a reason, a hard time budget, and an entry in PRIVACY.md.
- The product name lives in `routemap/__about__.py`; do not hard-code it.

## Licence

Route Map is licensed under the GNU AGPL-3.0 (see [LICENSE](LICENSE) and
[NOTICE](NOTICE)). Contributions are accepted under the CLA above.
