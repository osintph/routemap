"""
The one place the product is named.

The working name may change before the first release. Every runtime string that
names the product reads it from here: the distribution and executable name, the
window title, the User-Agent sent to Hoiho and the IP database, the config
directory, and the repository URL used by the explicit update check. The few
build-time literals that cannot import this module (pyproject.toml, the
PyInstaller spec, the release workflow) are listed in docs/renaming.md.
"""

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

__version__ = "0.2.0b1"

# Upstreams see this product token, so a complaint about our traffic reaches
# the project rather than whoever happens to be running it.
USER_AGENT_PRODUCT = f"{NAME}/{__version__}"
USER_AGENT = f"{USER_AGENT_PRODUCT} (+{REPO_URL})"


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
    try:
        root = pathlib.Path(__file__).resolve().parents[1]
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                             timeout=3)
        sha = out.stdout.strip()
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, timeout=3).stdout.strip()
        return (sha + ("+dirty" if dirty else " (source)")) if sha else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def version_line() -> str:
    """'0.2.0b2, commit 1a2b3c4d5e6f': what About, --version and the smoke test show."""
    commit = build_commit()
    return f"{__version__}, commit {commit[:12]}{commit[40:] if len(commit) > 40 else ''}"
