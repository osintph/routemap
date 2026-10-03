# Renaming the project

The working name is `routemap` (display name "Route Map"). Runtime strings read
it from `routemap/__about__.py` (`NAME`, `DISPLAY_NAME`, `REPO_SLUG`), so a
rename of what users see is a one-file change there.

A full rename also has to touch the literals that cannot import that module:

| Where | What |
|---|---|
| `routemap/` (directory) | the import package; rename it and update imports with one `sed` |
| `pyproject.toml` | `name`, `[project.scripts]`, the URLs, the hatch version path and wheel package |
| `packaging/build_nuitka.py` | output names (`routemap-app`, `routemap.exe`, `routemap-cli.exe`); display name from `__about__` |
| `packaging/linux/routemap.desktop`, `AppRun` | `Name=`, `Exec=`, `Icon=`, the binary path |
| `.github/workflows/build.yml` | artifact and file names, the dmg volume name |
| `packaging/release-notes-unsigned.md`, `README.md`, `PRIVACY.md` | prose |
| `docs/download-host/`, `scripts/testers.sh` (welcome email), `packaging/download_index.py` | prose |

`grep -rn -i "routemap\|route map" --exclude-dir=.git` after a rename should
find only imports and the lines above.
