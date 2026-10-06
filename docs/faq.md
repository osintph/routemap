# Questions

## Why does Windows or macOS warn me?

The builds are not code-signed or notarised yet. Windows signing with a Certum
code signing certificate is being set up. The steps to open the app anyway are in the
[troubleshooting guide](troubleshooting.md), and every file can be checked
against the GPG-signed checksums of its release.

## Why isn't the Windows build signed by a free open-source signing programme?

Free signing programmes for open-source projects exist, but they only accept
projects with established public adoption. Route Map is new, so Windows
releases will be signed with a Certum code signing certificate paid for by
the maintainer, once it is issued. Until then the Windows build is unsigned.

## Is it free?

Yes: free and open source under the GNU AGPL-3.0, with no ads, no account, and
no tracking in the app. Donations pay for code signing, hosting, the RIPE Atlas probe and
maintenance time.

## Where does a placement come from?

From the router's hostname first: CAIDA's Hoiho rules and carriers' own site
codes. Only if the hostname says nothing does it fall back to an IP geolocation
database (RIPEstat), and that answer must still pass the round-trip check. The
Source column and the marker colour say which. See
[reading the result](guide.md#reading-the-result).

## What does it send, and to whom?

Only what [PRIVACY.md](../PRIVACY.md) lists: public router hostnames to CAIDA
Hoiho, public hop addresses to RIPEstat, reverse DNS queries to your own
resolver, and, only if you have not set your location, your public IP to
RIPEstat. Private and carrier-NAT addresses are never looked up. Each source
can be switched off.

## Can I map a traceroute someone else ran?

Yes: File > Paste Trace, and say where it was run from. Output of `traceroute`,
`tracert` and `mtr --report` works.

## Does it need administrator rights?

No. It runs your system's own trace tool as you.

## Is there a command line?

Yes, on every platform: see the [command-line reference](cli.md).

## Does the app or the project site track me?

The desktop app has no telemetry. The website, getroutemap.app, counts visits
with Cloudflare Web Analytics, which sets no cookies, and keeps a download log
that stores no addresses. Analytics cookies are set only if you accept them in
the site's cookie banner, and you can change that choice at any time. The
site's privacy page has the details.

## Why are there no submarine cables on the map?

The well-known cable map is TeleGeography's. Its map images are licensed CC
BY-SA 4.0, but the cable and landing-point data behind them is sold under an
annual licence, so a free application cannot ship it. The overlay will come
back if an openly licensed source appears.

## Why no internet exchange points?

PeeringDB has the list of exchange prefixes, but its terms do not allow
reproducing or redistributing it without permission. Permission is being asked;
until PeeringDB agrees, hops at an exchange are shown like any other hop.

## Where does the AS number come from?

From DB-IP Lite ASN, bundled with the app (CC BY 4.0, IP Geolocation by
DB-IP), so the AS path works offline. With Online lookups on, RIPEstat adds the
routed prefix, RPKI state and the rest of the route summary.
