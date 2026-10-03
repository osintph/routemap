"""
Which online services this build may use, in one place.

CAIDA Hoiho: covered by CAIDA's Acceptable Use Agreement for Publicly
Accessible Datasets; publications must cite "The CAIDA UCSD Hoiho" (the PDF
report does).

RIPEstat: used under the RIPEstat Service Terms and Conditions. Setting
RIPESTAT_ALLOWED to False builds an app that never calls it: no IP database
fallback, no public-IP origin lookup and no Atlas network lookup. Hops are then
placed by hostname (Hoiho, site codes, PTR) only, and the user sets the origin
in Settings.

Changing a flag here is the whole switch: the settings page, the sources and
the origin lookup all read it.
"""

HOIHO_ALLOWED = True
RIPESTAT_ALLOWED = True

RIPESTAT_OFF_NOTE = ("This build does not use RIPEstat, so hops are placed from their "
                     "hostnames only and the origin must be set in Settings.")
