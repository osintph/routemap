# Permission request to PeeringDB

Draft for the maintainer to send. To: support@peeringdb.com. It asks for
written permission under the PeeringDB Acceptable Use Policy to include a
derived list of exchange peering LAN prefixes in a free desktop application.

---

**Subject:** Permission request: IXP peering LAN prefixes in an open-source traceroute map (Route Map)

Hello PeeringDB team,

I maintain Route Map (https://github.com/osintph/routemap), a free and open
source desktop application, licensed under the GNU AGPL-3.0, that runs a
traceroute on the user's own computer and draws the path on a world map. Its
geolocation engine is a separate AGPL-3.0 package, routemap-engine
(https://github.com/osintph/routemap-engine), which the FalconEye web tool by
the same maintainer also uses.

**What we would like to do.** When a traceroute hop's address falls inside an
internet exchange's peering LAN, label that hop with the exchange's name ("via
Equinix Singapore"), so users can see where their traffic crosses an exchange.
To do that we would like to use the `ixpfx` prefixes together with the
exchange name, city and country (`ix`, `ixlan`) from the PeeringDB API.

**How the data would be used.**

- **Bundled offline.** A derived table (prefix, exchange name, city, country;
  nothing else, no contact or network records) would ship inside the
  application, so that a traceroute is labelled without any request leaving
  the user's machine. The application's privacy rules are that hop addresses
  are never sent anywhere that is not needed, and an offline table keeps the
  lookup local.
- **Only for labelling hops.** The table is not exposed as a dataset, an API
  or a searchable directory. It is read only to match hop addresses in the
  user's own trace.
- **Attribution.** "Exchange data: PeeringDB (https://www.peeringdb.com)" in the
  application's About box, its third-party notices, on the map when a hop is
  labelled, and in every PDF or JSON export that shows an exchange.
- **Non-commercial.** The application is free of charge with no paid tier, no
  advertising and no account. The project is funded only by voluntary
  donations.
- **Update cadence.** The table would be regenerated from the public API at
  most once a month, at release time, by a single scripted run with an
  identifying User-Agent and, if you prefer, an API key you issue to us. End
  users' installations would never query PeeringDB themselves.
- **Source code.** Because the application is AGPL-3.0, the derived table
  would appear in its public source repository. If you would rather the table
  not be redistributed in source form, we can instead ship only the compiled
  table inside the application, or limit it to the fields above.

Until we hear from you, the feature is switched off in the code and no
PeeringDB data is included in any release.

Could you let us know whether this use is acceptable under the Acceptable Use
Policy, and on what conditions? We are happy to adjust the attribution wording,
the update cadence or the fields included.

Thank you,

The Route Map maintainer
support@getroutemap.app
