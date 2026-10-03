# Renaming the project

The working name is `routemap`. Runtime strings read it from
`routemap/__about__.py` (`NAME`, `DISPLAY_NAME`, `REPO_SLUG`), so a rename of
what users see is a one-file change there.

A full rename also has to touch the literals that cannot import that module:

| Where | What |
|---|---|
| `routemap/` (directory) | the import package; rename it and update imports with one `sed` |
| `pyproject.toml` | `name`, `[project.scripts]`, the URLs, the hatch version path and wheel package |
| `.github/workflows/*.yml` | artifact names (arrive with the build step) |
| FalconEye `requirements.txt` | the pinned dependency URL |

Nothing else should name the product. `grep -rn routemap --exclude-dir=.git`
after a rename should find only imports and the lines above.
