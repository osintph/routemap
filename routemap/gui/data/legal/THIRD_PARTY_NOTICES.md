# Third-party notices

The Route Map desktop application includes or uses the following components.
Each is used under its own licence; nothing in the application's licence
changes these terms.

## Bundled software

| Component | Licence | Source |
|---|---|---|
| routemap-engine | GNU AGPL-3.0 | https://github.com/osintph/routemap-engine |
| Qt 6 libraries | GNU LGPL-3.0 | https://download.qt.io/official_releases/qt/ |
| PySide6, shiboken6 (Qt for Python) | GNU LGPL-3.0 | https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| Python | PSF License 2.0 | https://www.python.org/ |
| httpx, httpcore, idna | BSD-3-Clause | https://pypi.org/project/httpx/ |
| h11, anyio | MIT | https://pypi.org/project/h11/ |
| dnspython | ISC | https://pypi.org/project/dnspython/ |
| certifi | MPL-2.0 | https://pypi.org/project/certifi/ |
| typing_extensions | PSF-2.0 | https://pypi.org/project/typing-extensions/ |
| maxminddb (reads the DB-IP files) | Apache-2.0 | https://pypi.org/project/maxminddb/ |
| Nuitka runtime (in compiled builds) | Apache-2.0 | https://nuitka.net/ |

**Qt and Qt for Python (LGPL-3.0).** The Qt libraries and the PySide6 and
shiboken6 modules are shipped as separate shared libraries inside the
application folder or bundle, unmodified. You may replace them with your own
builds of the same versions; the application loads them at run time. The full
text of the LGPL-3.0, GPL-3.0, AGPL-3.0, MPL-2.0 and Apache-2.0 is included
with every build (Help > Third-Party Notices), and the
corresponding source is available at the addresses above. On request, the
copyright holder will provide the exact version information for any build.

**routemap-engine (AGPL-3.0).** Complete corresponding source for the version
in each build is at https://github.com/osintph/routemap-engine under the tag
named in the application's About box.

## Data

| Data | Licence | Attribution |
|---|---|---|
| City list | Creative Commons Attribution 4.0 | GeoNames, https://www.geonames.org/ |
| World map, 1:50m and 1:10m, populated places | Public domain | Natural Earth, https://www.naturalearthdata.com/ |
| IP to ASN (bundled) and IP to City (downloaded on request) | Creative Commons Attribution 4.0, https://creativecommons.org/licenses/by/4.0/ | IP Geolocation by DB-IP, https://db-ip.com |
| Carrier site codes | Facts from the carrier's own published router list | Arelion looking glass, https://lg.twelve99.net/ |

## Online services the application queries

Not bundled; each has its own terms, which apply to the queries it receives.

| Service | Used for | Terms |
|---|---|---|
| CAIDA Hoiho | router hostname rules | CAIDA Acceptable Use Agreement for Publicly Accessible Datasets; publications must cite "The CAIDA UCSD Hoiho" |
| RIPEstat (RIPE NCC) | IP geolocation fallback, public IP and network lookups, RPKI, RIS, BGP updates, AS overview, abuse contacts | RIPEstat Service Terms and Conditions |
| RIPE Atlas (RIPE NCC) | anchor mesh baselines (public data); traces and history with the user's own key | RIPE Atlas Terms and Conditions |
| DB-IP | downloading the DB-IP Lite files, when the user asks | DB-IP Lite licence, CC BY 4.0 |
| GitHub | the explicit update check | GitHub Terms of Service |
