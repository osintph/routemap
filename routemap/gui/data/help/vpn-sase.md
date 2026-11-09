## Using {NAME} behind a VPN or SASE client

A VPN or SASE client changes what a trace can see. {NAME} tells you when it can detect that, but what it measures is still the path your packets took.

### Why a trace can mislead here

1. **The origin can be wrong.** On Auto, your origin comes from your public IP address. Behind a tunnel, that is usually the provider's exit, not where you are. RTT checks are anchored on the origin, so correct hops can be rejected and wrong ones accepted. Set your real location in Settings > Origin.
2. **TCP can be intercepted.** Some clients proxy TCP on port 443, so the "target" that answers is a local or nearby proxy. Paths on Windows probes TCP 443, so it can be affected. RTTs and hops from such a run mean little.
3. **Hops can be hidden.** The path between this computer and the provider's entry point can collapse into one or two hops, or none, and tunnel overhead adds to every RTT.
4. **ICMP and TCP can take different routes.** Depending on the client's policy, a Trace (ICMP) and Paths (TCP on Windows) can measure different routes in the same session.

### What the notices mean

- **"Traffic to this target goes through [adapter]."** The route to this target uses a tunnel adapter. The name is the one your system reports. The map shows the path through it, not the direct internet path.
- **The origin warning** appears when the origin is on Auto and your system's default route, so your internet traffic, goes through a tunnel. A tunnel that carries only some targets does not change your public IP and gets no warning. {NAME} does not change the origin for you.
- **"TCP results are unreliable."** A TCP connection completed or was refused at TTL 2 or less, where a real probe must die at a router. It does not count if the target is on your local subnet, or if an ICMP echo reaches it at the same TTL. The export names the condition that triggered it.
- **"TCP and ICMP left by different first hops."** Shown only when both protocols got an answer from hop 1 and the answers differ.

An adapter your system does not clearly describe is listed as "unclassified". It is named in the Interface section of the route summary and in exports, with no notice over the result.

### The probe interface

Settings > Trace > Probe interface lists the adapters your system reports, with their kind, state and addresses. Automatic (system route) is the default. On the command line, use `-i NAME` and `--list-interfaces`.

It applies to Trace, Paths and Watch. DNS timing and port tests keep the system route, and an agent probes from its own network.

Limits:

- Some clients intercept traffic in their driver and ignore which adapter a program asks for. After a run on a chosen interface, hop 1 is compared with that adapter. If hop 1 belongs to another adapter, the result says "Probes were redirected by [adapter]; the selected interface was not used." If it cannot tell, the result says so. Neither case is presented as a direct path.
- A connected VPN can disable a physical adapter's default route. The run then stops with a plain "no route" message, and nothing is sent through any other adapter.
- Choosing a physical adapter while a tunnel is up may bypass your organisation's security path. {NAME} tells you once, and it is your choice. It never selects an interface by itself.

### Seeing the real internet path

A trace from inside the tunnel cannot show the path outside it. Two things can:

- **A remote agent** (Settings > Agents) runs the trace from a server outside the tunnel.
- **A RIPE Atlas reverse trace** measures from a probe near the target back toward you.

### Privacy

The adapter list, addresses and gateways are read locally and never sent anywhere. Exports carry the adapter's kind and name. Addresses and gateways go into an export only when you tick the checkbox in the Export dialog.
