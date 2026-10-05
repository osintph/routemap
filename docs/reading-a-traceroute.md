# How to read a traceroute

A traceroute lists the routers your traffic passes on its way to a destination,
one line per hop, with how long each router took to answer. Read it from the
top: the first lines are your own network, the last line is the destination.

## One line per hop

Each line has a hop number, the router's name and address, and usually three
round-trip times in milliseconds. The name, when there is one, is the reverse
DNS name its operator gave it, and it often says more than the address: many
operators put a city or airport code in it, such as `fra` for Frankfurt or
`sjc` for San Jose.

## Round-trip times

A round-trip time is how long the probe took to reach that router and for its
answer to come back. Times grow along the path, and a large step between two
hops usually means a long distance: crossing an ocean adds tens of
milliseconds, because light in fibre covers about 200 km per millisecond.

A time can also drop at a later hop. That is normal. Routers answer traceroute
probes with low priority, so a busy router can look slow while the traffic it
forwards is not. A hop is only a problem if the slowness carries on to every
hop after it.

## Stars

A `*` means no answer arrived in time. Many routers do not answer traceroute
probes at all, or limit how often they answer. Stars in the middle of a path,
followed by hops that answer, are not a fault: the traffic got through. Stars
to the end can mean the destination does not answer probes, or that something
on the way drops them.

## Several addresses on one hop

Large networks spread traffic over parallel links, so the three probes of one
hop can be answered by different routers. That is load balancing, not an error.

## What a traceroute cannot show

It shows the path out, not the way back, which can be entirely different. It
shows where routers answer from, not every device on the way. And a router's
location is never in the trace itself: it has to be worked out from its name,
from an IP database, or from the times.

## How Route Map shows it

Route Map draws the same hops on a map and puts the reading above into the
picture: each step's added round-trip time is the colour of its line, and every
placement is checked against the time it took, so a router cannot be drawn on a
continent its answer could not have come from. Each hop says whether its place
came from the operator's hostname, an IP database, or nowhere. See the
[user guide](guide.md).
