# Known limitations

- **Unsigned builds.** Windows builds are not code-signed until signing with
  the maintainer's Certum certificate is set up, and macOS builds are not notarised, so both
  systems warn on first start.
- **Platforms.** Windows x86_64, macOS 12+ (Apple silicon and Intel) and Linux
  x86_64. No Windows on ARM or Linux ARM builds yet.
- **IP database placements are hints.** The fallback database places a
  backbone address where its operator registered the prefix, which can be a
  head office far from the router. Route Map rejects placements the round trip
  rules out, but a wrong city that is still within reach is shown, labelled
  `ip-db`. Some addresses are known only to a country (hollow marker).
- **The physics bound is an upper limit.** It proves a hop cannot be farther
  than about 100 km per millisecond of round trip; it cannot prove a hop is
  where a source says. Slow replies (routers answer ICMP at low priority) only
  loosen the bound, never tighten it.
- **What traceroute cannot see.** MPLS tunnels hide hops, the return path can
  differ from the forward path, and hops that do not answer are listed but not
  placed.
- **Origin from your public IP** is a city-level guess and is wrong behind a
  VPN or proxy; set the origin in Settings.
- **Repeated hops at one place.** Hops at the same place that are not next to
  each other in the trace get separate markers; at world zoom the labels can
  spread far apart, with thin leader lines back to the real point. Zoom in to
  see them together.
- **Hostname rules cover the operators Hoiho and the bundled site-code table
  know.** A carrier with an unknown naming scheme falls back to the database;
  reports of such schemes are welcome.
- **No submarine cables.** TeleGeography's cable data is sold under licence
  (only its map images are CC BY-SA), so there is no cable overlay until a
  source the app may ship exists.
- **No internet exchange labels.** PeeringDB's terms do not allow bundling its
  prefix list; the code is there, switched off, pending their permission.
- **ASN data is DB-IP's ranges, not BGP prefixes.** The offline AS number is
  from DB-IP Lite ASN; the routed prefix and RPKI come from RIPEstat when
  Online lookups are on.
- **Anycast is a likelihood.** "Likely anycast" means the destination answered
  too fast for where it is registered, or belongs to a large content network;
  the served-from city is the largest one the RTT can reach.
- **The typical latency is between countries**, from the nearest RIPE Atlas
  anchors to the origin and the destination; small countries with no anchor
  have no baseline.
