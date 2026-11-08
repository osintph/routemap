"""What the app says about the adapter a trace went through and about a TCP
Paths run that something answered too close. One place, Qt-free, so the window,
the CLI and the exports say the same thing."""
from __future__ import annotations

import html

from routemap.__about__ import DISPLAY_NAME

TUNNEL, PHYSICAL, UNCLASSIFIED = "tunnel", "physical", "unclassified"
CHECKS = ("consistent", "redirected", "unconfirmed", "no_route")

# Links inside the notice bar (gui/app.py opens them).
LINK_HELP, LINK_ORIGIN, LINK_AGENTS, LINK_REVERSE = "help:vpn", "settings:origin", "settings:agents", "reverse:run"


def block_of(use) -> dict | None:
    """An engine InterfaceUse as the dict the app keeps with a result, in
    memory only: the addresses leave it unless the user ticks the export box."""
    return None if use is None else {**use.to_export(include_addresses=True), "description": use.description}


def stored(block: dict | None) -> dict | None:
    """The block as a history entry or an export keeps it: no local addresses."""
    if not block:
        return None
    return {k: block[k] for k in ("kind", "label", "selected", "check", "redirected_by") if k in block}


def banner(block: dict | None, *, fresh: bool = True) -> str | None:
    """For a tunnel adapter only: an unclassified one (a virtual switch every
    run goes through, say) is named in the details panel and the export."""
    if not block or block.get("kind") != TUNNEL:
        return None
    return (f"Traffic to this target goes through {block['label']}. " if fresh else
            f"This trace went through {block['label']}. ") + \
        "The map shows the path through it, not the direct internet path."


def origin_warning(block: dict | None, origin_auto: bool) -> str | None:
    if not origin_auto or not block or block.get("kind") != TUNNEL:
        return None
    return "Origin is on Auto, so it comes from your public IP, which is probably the tunnel or SASE exit."


def check_line(block: dict | None) -> str | None:
    """The hop-1 check after a run on a chosen interface, when there is
    something to say. A run that looks right is still no proof of a direct path."""
    if not block or not block.get("selected"):
        return None
    check, label = block.get("check"), block.get("label")
    if check == "redirected":
        return f"Probes were redirected by {block.get('redirected_by')}; the selected interface was not used."
    if check == "unconfirmed":
        return f"Could not confirm that the probes left through {label}."
    if check == "no_route":
        return (f"{label} has no route to the target. A connected VPN can disable this adapter's default route. "
                "Nothing was sent through any other adapter.")
    return None


def details_text(block: dict | None) -> str | None:
    """One line for the details panel and the PDF."""
    if not block:
        return None
    return f"{block['label']} ({block['kind']})" + (", chosen in Settings" if block.get("selected") else "") + \
        ("; hop 1 matches it" if block.get("check") == "consistent" else "")


_HOW = {"completed": "a TCP connection completed", "refused": "a TCP connection was refused"}


def interception_line(paths: dict | None) -> str | None:
    found = (paths or {}).get("interception") or {}
    if not found.get("intercepted"):
        return None
    parts = str(found.get("condition") or "").split("_")
    how = _HOW.get(parts[1] if len(parts) > 1 else "", "a TCP connection ended")
    return (f"TCP results are unreliable: {how} {('at TTL ' + parts[-1]) if parts[-1].isdigit() else 'too close'}, "
            "so something local or adjacent answered in the target's place.")


def split_line(paths: dict | None) -> str | None:
    split = ((paths or {}).get("interception") or {}).get("split_hop1")
    if not split:
        return None
    return (f"TCP and ICMP left by different first hops ({split['tcp']} and {split['icmp']}), "
            "so a Trace and Paths can measure different routes here.")


ALTERNATIVES = "To see the internet path from outside it, run from a remote agent or a RIPE Atlas reverse trace."
INSTEAD = "Use an ICMP Trace, a remote agent or a RIPE Atlas reverse trace instead."


def plain_lines(block: dict | None, paths: dict | None, *, origin_auto: bool = False, fresh: bool = True) -> list[str]:
    """Every note for this result, as text (the CLI, the PDF)."""
    out = []
    if banner(block, fresh=fresh):
        out.append(banner(block, fresh=fresh) + " " + ALTERNATIVES)
    if origin_warning(block, origin_auto):
        out.append(origin_warning(block, origin_auto) + " Set one with --origin or in Settings > Origin.")
    if check_line(block):
        out.append(check_line(block))
    if interception_line(paths):
        out.append(interception_line(paths) + " " + INSTEAD)
    if split_line(paths):
        out.append(split_line(paths))
    return out


def _link(href: str, text: str) -> str:
    return f"<a href='{href}'>{text}</a>"


def notice_html(block: dict | None, paths: dict | None, *, origin_auto: bool = False, fresh: bool = True) -> str:
    """The non-blocking bar over a result, or "" when there is nothing to say."""
    out = []
    e = html.escape
    elsewhere = _link(LINK_AGENTS, "Run from an agent") + " &middot; " + _link(LINK_REVERSE, "RIPE Atlas reverse trace")
    if banner(block, fresh=fresh):
        out.append(e(banner(block, fresh=fresh)) + " " + _link(LINK_HELP, "Help") + " &middot; " + elsewhere)
    if origin_warning(block, origin_auto):
        out.append(e(origin_warning(block, origin_auto)) + " " + _link(LINK_ORIGIN, "Set origin…"))
    if check_line(block):
        out.append(e(check_line(block)) + " " + _link(LINK_HELP, "Help"))
    if interception_line(paths):
        out.append("<b>" + e(interception_line(paths)) + "</b> " + e(INSTEAD) + " " + elsewhere)
    if split_line(paths):
        out.append(e(split_line(paths)))
    return "<br>".join(out)


def adapter_row(adapter) -> str:
    """One line of the interface list: the OS's name and description, kind,
    state, addresses. Wireshark's list, in words."""
    name = adapter.name + (f" ({adapter.description})" if adapter.description else "")
    state = "up" if adapter.up else "down"
    return f"{name}, {adapter.kind}, {state}" + (f", {', '.join(adapter.addresses)}" if adapter.addresses else "")


def bypass_applies(adapter, adapters) -> bool:
    """A physical adapter chosen while a tunnel adapter is up."""
    return adapter is not None and adapter.kind == PHYSICAL and any(
        a.kind == TUNNEL and a.selectable and a.addresses for a in adapters)


BYPASS_NOTICE = ("A tunnel adapter is up on this computer. Probing out of a physical adapter may bypass your "
                 "organisation's security path. It is your choice, and " + DISPLAY_NAME +
                 " never selects an interface by itself.")
