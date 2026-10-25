"""
Remote agents (0.5.0-beta.1): a trace measured on a server the user reaches
with their own ssh client, shown with that server as its origin. Qt-free.

An agent is a name, an ssh destination (a Host from the user's ssh config, or
user@host), where to put it on the map, and whether its first hops are shown.
Nothing else is stored: keys, passwords and host keys stay with ssh. Each run
is one ``ssh -T -o BatchMode=yes`` command (routemap_engine.agent builds it,
every argument validated and quoted), started by a click, never retried and
never run in the background.

The server runs ``routemap-engine agent 1 ...`` and only measures. Placing
hops, AS paths and every lookup happen here with this computer's Sources
settings. The server's first hops are its provider's network and are masked
unless the agent's "Show first hops" is on; the server's own address never
reaches this app (the agent prints only its place).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from typing import Callable

from routemap_engine import agent as engine_agent

MAX_AGENTS = 20
PLACE_IP = "ip"
PLACE_CITY = "city"
_NAME = re.compile(r"[^\x00-\x1f\x7f<>]{1,40}")
# Extra time past the agent's own deadline before this app stops waiting.
GRACE_SECONDS = 30.0
STDERR_CAP = 4096


class AgentFailed(RuntimeError):
    """A remote run that produced nothing usable; ``str()`` says why, for the user."""


@dataclass
class Agent:
    name: str
    destination: str
    place: str = PLACE_IP                    # "ip": the server's place, looked up on the server; "city"
    city: str = ""                           # the city label when place is "city"
    lat: float | None = None
    lon: float | None = None
    show_first_hops: bool = False            # the server provider's first hops, masked unless on
    command: str = ""                        # the engine command on the server; "" is routemap-engine

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data) -> "Agent | None":
        """An agent from settings, or None when any field fails its check."""
        if not isinstance(data, dict):
            return None
        name = str(data.get("name") or "").strip()
        if not _NAME.fullmatch(name):
            return None
        try:
            dest = engine_agent.validate_destination(str(data.get("destination") or ""))
            command = str(data.get("command") or "").strip()
            if command:
                command = engine_agent.validate_command(command)
        except engine_agent.AgentError:
            return None
        place = data.get("place") if data.get("place") in (PLACE_IP, PLACE_CITY) else PLACE_IP
        lat, lon = data.get("lat"), data.get("lon")
        try:
            lat = None if lat is None else round(float(lat), 2)
            lon = None if lon is None else round(float(lon), 2)
        except (TypeError, ValueError):
            lat = lon = None
        if lat is not None and not (-90 <= lat <= 90 and -180 <= (lon or 0) <= 180):
            lat = lon = None
        city = str(data.get("city") or "")[:120]
        if place == PLACE_CITY and (lat is None or lon is None):
            place, city = PLACE_IP, ""
        return cls(name, dest, place, city if place == PLACE_CITY else "", lat if place == PLACE_CITY else None,
                   lon if place == PLACE_CITY else None, bool(data.get("show_first_hops")), command)

    @property
    def place_text(self) -> str:
        return self.city if self.place == PLACE_CITY and self.city else "from its public IP"


def clean(value) -> list[dict]:
    """The agents a settings file holds, each checked; unique names, at most
    :data:`MAX_AGENTS`."""
    out, names = [], set()
    for item in value if isinstance(value, list) else []:
        a = Agent.from_dict(item)
        if a is None or a.name.lower() in names:
            continue
        names.add(a.name.lower())
        out.append(a.to_dict())
    return out[:MAX_AGENTS]


def all_agents(settings) -> list[Agent]:
    return [a for a in (Agent.from_dict(d) for d in settings.agents or []) if a is not None]


def by_name(settings, name: str | None) -> Agent | None:
    return next((a for a in all_agents(settings) if a.name == name), None) if name else None


def find_ssh() -> str | None:
    """The user's ssh client: on PATH, or Windows' own OpenSSH Client (a
    Windows feature from Windows 10 build 1809, Microsoft Learn)."""
    found = shutil.which("ssh")
    if found:
        return found
    if sys.platform.startswith("win"):
        own = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
        if os.path.isfile(own):
            return own
    return None


SSH_MISSING = ("No ssh client was found. Remote agents use your own ssh: on Windows add the "
               "\"OpenSSH Client\" optional feature; macOS and most Linux systems have ssh already.")


def run(agent: Agent, action: str, settings, *, target: str | None = None, ports=None,
        on_line: Callable[[str], None] | None = None, on_progress: Callable[[dict], None] | None = None,
        cancel: threading.Event | None = None, ssh: str | None = None, popen=subprocess.Popen,
        online: bool = True) -> engine_agent.AgentRun:
    """One remote run of *action* ("hello", "trace", "paths", "ports") on
    *agent*. Blocking: a worker thread. Raises AgentFailed when ssh or the
    agent produced nothing usable."""
    ssh = ssh or find_ssh()
    if not ssh:
        raise AgentFailed(SSH_MISSING)
    deadline = float(settings.timeout_seconds) if action == "trace" else engine_agent.MAX_DEADLINE
    kw = {}
    if action != "hello":
        kw = dict(target=target, family=settings.ip_version, resolvers=list(settings.dns_resolvers),
                  wait=settings.port_wait, deadline=deadline)
        if action == "paths":
            kw["budget"] = settings.paths_budget
        if action == "ports" or ports is not None:
            kw["ports"] = ports if ports is not None else settings.port_list
            kw["tls_ports"] = settings.tls_ports
    line = engine_agent.remote_command(action, command=agent.command or None,
                                       place_from_ip=agent.place == PLACE_IP and online, **kw)
    argv = engine_agent.ssh_argv(ssh, agent.destination, line)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
    try:
        proc = popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                     creationflags=flags)
    except OSError as exc:
        raise AgentFailed(f"ssh could not be started: {exc}") from exc
    err = bytearray()

    def drain():
        for chunk in iter(lambda: proc.stderr.read(512), b""):
            if len(err) < STDERR_CAP:
                err.extend(chunk[:STDERR_CAP - len(err)])
    readers = [threading.Thread(target=drain, name="routemap-agent-stderr", daemon=True)]
    stop_at = time.monotonic() + deadline + GRACE_SECONDS
    stopped = {"by": None}

    def watch():
        while proc.poll() is None:
            if cancel is not None and cancel.is_set():
                stopped["by"] = "cancel"
            elif time.monotonic() > stop_at:
                stopped["by"] = "deadline"
            if stopped["by"]:
                try:
                    proc.kill()                  # closes the session; the agent stops on stdin EOF
                except OSError:
                    pass
                return
            time.sleep(0.1)
    readers.append(threading.Thread(target=watch, name="routemap-agent-watch", daemon=True))
    for t in readers:
        t.start()
    try:
        result = engine_agent.read_run(proc.stdout, on_line=on_line, on_progress=on_progress)
    except BaseException:
        # Ctrl+C in the CLI, or anything else: close the session now, so the
        # agent stops on its stdin closing instead of running on.
        try:
            proc.kill()
        except OSError:
            pass
        raise
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
        rc = proc.wait()
        readers[0].join(timeout=1.0)
    if stopped["by"] == "cancel":
        raise AgentFailed("Stopped.")
    if stopped["by"] == "deadline":
        raise AgentFailed(f"{agent.name} did not finish in time; the run was stopped.")
    if result.hello is None and rc == 255:
        raise AgentFailed(f"ssh could not connect to {agent.destination}: {_ssh_reason(bytes(err))}")
    if result.error and result.result is None:
        raise AgentFailed(f"{agent.name}: {result.error}")
    return result


def _ssh_reason(stderr: bytes) -> str:
    """The last line ssh printed, which says why it gave up (host key,
    authentication, timeout), made safe to show."""
    lines = [ln.strip() for ln in stderr.decode("utf-8", "replace").splitlines() if ln.strip()]
    text = lines[-1] if lines else "no reason given"
    return "".join(ch for ch in text if ch.isprintable())[:300]


def origin_of(agent: Agent, run: engine_agent.AgentRun) -> tuple[float, float, str] | None:
    """Where the agent is on the map: its city, or the place it looked up."""
    if agent.place == PLACE_CITY and agent.lat is not None and agent.lon is not None:
        return agent.lat, agent.lon, agent.city or f"{agent.lat}, {agent.lon}"
    if run.origin:
        return run.origin["lat"], run.origin["lon"], run.origin.get("label") or f"{run.origin['lat']}, {run.origin['lon']}"
    return None


def origin_how(agent: Agent, run: engine_agent.AgentRun) -> str:
    return "agent-city" if agent.place == PLACE_CITY else ("agent-ip" if run.origin else "first-hop")


def finish(agent: Agent, body: dict, text: str) -> tuple[dict, str, list[str]]:
    """Mask the provider's first hops of an agent route unless the agent shows
    them; returns (route dict, tool text, masked addresses)."""
    if agent.show_first_hops:
        return body, text, []
    masked = engine_agent.mask_first_hops(body)
    return body, engine_agent.mask_text(text, masked), masked


def remote_result(agent: Agent, action: str, target: str, run, settings, on_progress=None) -> dict:
    """An agent's answer analysed here, with this computer's Sources settings,
    from the agent's place, the provider's first hops masked unless shown."""
    import asyncio

    from routemap import service
    from routemap_engine import Route
    res = run.result
    origin = origin_of(agent, run)
    point = origin[:2] if origin else None
    prog = (lambda a, b, c: on_progress(a, b, c)) if on_progress else None
    if action == "paths":
        from routemap_engine import analyse_paths
        d = res["discovery"]
        route = asyncio.run(analyse_paths(d, point, sources=service.sources_for(settings), progress=prog))
        text, argv = d.trace_text(), [f"ssh {agent.name}", d.method, f"{d.flows_used} flows",
                                      f"{d.probes_sent} probes", target]
    else:
        route = service.analyse_sync(res["trace_text"], point, settings, progress=prog)
        text, argv = res["trace_text"], [f"ssh {agent.name}", res.get("tool") or "trace", target]
    body = route.to_dict()
    body["resolved"], body["dns"] = res["resolved"], res["dns"]
    if res.get("ports"):
        body["ports"] = res["ports"]
    body, text, _masked = finish(agent, body, text)
    return {"route": Route.from_dict(body), "text": text, "argv": argv,
            "origin_how": origin_how(agent, run),
            "agent": {"name": agent.name, "place": origin[2] if origin else None,
                      "first_hops_masked": not agent.show_first_hops}}
