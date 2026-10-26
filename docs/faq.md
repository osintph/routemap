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
database: DB-IP Lite City on your machine first, then RIPEstat online for the
addresses DB-IP Lite does not place. That answer must still pass the round-trip
check. The
Source column and the marker colour say which. See
[reading the result](guide.md#reading-the-result).

## What does it send, and to whom?

Only what [PRIVACY.md](../PRIVACY.md) lists: public router hostnames to CAIDA
Hoiho, public hop addresses DB-IP Lite does not place to RIPEstat, reverse DNS queries and the target's
own lookup to your resolver (and to any resolver you add in Settings >
Probes), and, only if you have not set your location, your public IP to
RIPEstat. Private and carrier-NAT addresses are never looked up. Each source
can be switched off.

## Can I map a traceroute someone else ran?

Yes: File > Paste Trace, and say where it was run from. Output of `traceroute`,
`tracert` and `mtr --report` works.

## Does it need administrator rights?

No. It runs your system's own trace tool, or its built-in prober, as you.
Port tests and DNS timing need no rights either.

## Can it watch a route over time?

Yes: **Watch**, or `routemap --watch TARGET`, probes every hop once a second,
mtr style, with per-hop loss, latency and jitter, a ping plot and the path
changes. It never goes faster than mtr's own defaults (one cycle a second, at
most 30 probes a second) and stops by itself after an hour unless you choose
longer, 8 hours at most. See the [guide](guide.md#continuous-mode).

## Is Ports a port scanner?

No. It tries one connection to each of at most 32 single ports you list, on
the one address you traced, four at a time. It refuses ranges and lists of
hosts. It answers "can I reach this service from here?", not "what runs on
this host?". See the [guide](guide.md#port-tests).

## Can I trace from somewhere else?

Yes, from a server you can reach with ssh: install `routemap-engine` there and
add it in Settings > Agents. Route Map runs one command there per trace with
your own ssh client and stores no keys or passwords. See the
[guide](guide.md#remote-agents).

## Paths says the routers do not answer TCP probes. What does that mean?

On Windows, Paths probes with TCP connection attempts. Some networks answer
ICMP but not TCP probes past some hop, so Paths cannot see the routers there;
use Trace, which probes with ICMP. If the target itself answers ICMP at that
hop while its TCP service answers only to the last attempts, something in
front of the target (a firewall or load balancer) is the likely reason, and
the heading says that instead.

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
