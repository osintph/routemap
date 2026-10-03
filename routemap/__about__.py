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

__version__ = "0.1.0b3"

# Upstreams see this product token, so a complaint about our traffic reaches
# the project rather than whoever happens to be running it.
USER_AGENT_PRODUCT = f"{NAME}/{__version__}"
USER_AGENT = f"{USER_AGENT_PRODUCT} (+{REPO_URL})"
