"""
The one place the product is named.

The working name may change before the first release. Every runtime string that
names the product reads it from here: the distribution and executable name, the
window title, the User-Agent sent to Hoiho and the IP database, the config
directory, and the repository URL used by the explicit update check. The few
build-time literals that cannot import this module (pyproject.toml, the
PyInstaller spec, the release workflow) are listed in docs/renaming.md.
"""

import re

# Distribution, import-facing and executable name.
NAME = "routemap"
# What a person reads: window title, PDF header, About box.
DISPLAY_NAME = "Route Map"
# GitHub owner/repo, for the explicit update check and the User-Agent contact.
REPO_SLUG = "osintph/routemap"
REPO_URL = f"https://github.com/{REPO_SLUG}"
# The project site and the one public contact address.
SITE_URL = "https://getroutemap.app"
# False until the project site is approved: the app then does not link it
# (About box, Support dialog). One switch.
SITE_LINKED = False
CONTACT_EMAIL = "support@getroutemap.app"
# Donations, in the order they are shown everywhere (Help > Support Route Map,
# README, the site's donate page, .github/FUNDING.yml).
DONATE_URL = f"{SITE_URL}/donate/"
DONATE_LINKS = (("Ko-fi", "https://ko-fi.com/osintph"), ("PayPal", "https://paypal.me/osintph"))
DONATE_ADDRESSES = (
    ("Bitcoin", "bc1q8hn6knzpkp0f2s06qncljpcsatv9dlqan5ttjv"),
    ("Monero", "42kA1yiEM8GSan4FeeZ9MxGtZCLNwYsvGefWLrMJ849dV2o9eVrc1Pufc7LcBAbRebXbVdxC5eoKj1a8pXJ3fSuFUDKLtXM"),
)
DONATIONS_PAY_FOR = "code signing, hosting, the RIPE Atlas probe, and maintenance time"
# True once Windows builds are code-signed (Certum certificate): the About box
# then says so.
WINDOWS_SIGNED = False

# PEP 440, for Python packaging only. Everything a person sees (About,
# --version, file names, installer, packages, User-Agent) uses VERSION.
__version__ = "0.2.0b4"


def display_version(version: str = __version__) -> str:
    """'0.2.0b2' -> '0.2.0-beta.2', the release tag's spelling without the v."""
    m = re.fullmatch(r"(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?", version)
    if not m:
        return version
    base, kind, n = m.groups()
    return base + (f"-{ {'a': 'alpha', 'b': 'beta', 'rc': 'rc'}[kind]}.{n}" if kind else "")


VERSION = display_version()

# Upstreams see this product token, so a complaint about our traffic reaches
# the project rather than whoever happens to be running it.
USER_AGENT_PRODUCT = f"{NAME}/{VERSION}"
USER_AGENT = f"{USER_AGENT_PRODUCT} (+{REPO_URL})"


def _git(folder) -> list[str] | None:
    """git -C *folder*, or None. Only for a checkout (a folder with .git), and
    only a git in an absolute PATH folder: never one in the current folder,
    which Windows and a relative PATH entry would otherwise find first (RM-03)."""
    import os
    import pathlib
    if not (pathlib.Path(folder) / ".git").exists():
        return None
    name = "git.exe" if os.name == "nt" else "git"
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        exe = os.path.join(entry, name)
        if os.path.isabs(entry) and os.path.isfile(exe) and os.access(exe, os.X_OK):
            return [exe, "-C", str(folder)]
    return None


def build_commit() -> str:
    """The commit a packaged build was made from (stamped by
    packaging/build_nuitka.py into routemap/_build.py), or the working tree's
    commit when run from source, or "unknown"."""
    try:
        from routemap._build import COMMIT  # type: ignore[import-not-found]
        return COMMIT
    except ImportError:
        pass
    import pathlib
    import subprocess
    git = _git(pathlib.Path(__file__).resolve().parents[1])
    if git is None:
        return "unknown"
    try:
        out = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=3)
        sha = out.stdout.strip()
        dirty = subprocess.run([*git, "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, timeout=3).stdout.strip()
        return (sha + ("+dirty" if dirty else " (source)")) if sha else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def engine_commit_from_metadata() -> str | None:
    """The installed engine's commit when it is not a published release: pip
    records one (PEP 610 direct_url.json) for an install from git, and a local
    checkout has its own. None for a release from PyPI, which records none."""
    import json
    import pathlib
    import subprocess
    from importlib import metadata
    try:
        direct = metadata.distribution("routemap-engine").read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return None
    if not direct:
        return None
    info = json.loads(direct)
    if "vcs_info" in info:
        return info["vcs_info"].get("commit_id") or "unknown"
    url = info.get("url", "")
    if url.startswith("file://"):
        git = _git(url[len("file://"):])
        if git is None:
            return "unknown"
        try:
            out = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=3)
            return out.stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            return "unknown"
    return "unknown"


def engine_line() -> str:
    """'routemap-engine 0.4.0', or with the commit while the app is not pinned to a release."""
    try:
        from routemap_engine.__about__ import __version__ as version
    except ImportError:
        return "routemap-engine (not installed)"
    try:
        from routemap._build import ENGINE_COMMIT  # type: ignore[import-not-found]
    except ImportError:
        ENGINE_COMMIT = engine_commit_from_metadata()
    if not ENGINE_COMMIT:
        return f"routemap-engine {version}"
    return f"routemap-engine {version}, commit {ENGINE_COMMIT[:12]} (not a release)"


def version_line() -> str:
    """'0.2.0-beta.2, commit 1a2b3c4d5e6f': what About, --version and the smoke test show."""
    commit = build_commit()
    return f"{VERSION}, commit {commit[:12]}{commit[40:] if len(commit) > 40 else ''}"
