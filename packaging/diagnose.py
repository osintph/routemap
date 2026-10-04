"""Platform diagnostics for parity work: what the trace tools print, which
probe types work unprivileged, and how every RIPEstat and Atlas call fares.

    python packaging/diagnose.py TARGET > diag.json

Run by .github/workflows/diagnose.yml (manual) on all three runners. Prints
JSON; contacts only the trace target, RIPEstat and RIPE Atlas.
"""
from __future__ import annotations

import asyncio
import json
import platform
import shutil
import subprocess
import sys
import time

from routemap import config, insight, service
from routemap_engine import analyse_sync, ripe


def run(argv: list[str], timeout: int = 150) -> dict:
    t = time.time()
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, errors="replace")
        return {"argv": argv, "code": p.returncode, "seconds": round(time.time() - t, 1),
                "out": p.stdout[-6000:], "err": p.stderr[-1500:]}
    except Exception as exc:  # noqa: BLE001
        return {"argv": argv, "error": repr(exc), "seconds": round(time.time() - t, 1)}


def main(target: str) -> int:
    out = {"platform": platform.platform(), "python": sys.version.split()[0], "tools": {}}
    if sys.platform.startswith("win"):
        out["tools"]["tracert"] = run(["tracert", "-d", "-h", "30", "-w", "1000", target])
    else:
        tr = shutil.which("traceroute") or "/usr/sbin/traceroute"
        out["tools"]["traceroute_udp"] = run([tr, "-n", "-m", "30", "-q", "3", "-w", "1", target])
        out["tools"]["traceroute_icmp"] = run([tr, "-I", "-n", "-m", "30", "-q", "3", "-w", "1", target])
        out["tools"]["traceroute_tcp"] = run([tr, "-T" if sys.platform.startswith("linux") else "-P",
                                              *([] if sys.platform.startswith("linux") else ["tcp"]),
                                              "-n", "-m", "30", "-q", "3", "-w", "1", target])
    text = next((v.get("out") for v in out["tools"].values() if v.get("out") and "ms" in v.get("out", "")), "")
    # Every RIPEstat call, timed.
    calls = []
    orig = ripe.RipeStat.call

    async def timed(self, endpoint, **params):
        t = time.time()
        data = await orig(self, endpoint, **params)
        calls.append({"endpoint": endpoint, "ok": data is not None, "seconds": round(time.time() - t, 2)})
        return data
    ripe.RipeStat.call = timed
    s = config.Settings()
    if text:
        route = analyse_sync(text, (51.5, -0.1), sources=service.sources_for(s)).to_dict()
        ins = insight.offline(route, s)
        t = time.time()
        asyncio.run(insight.online(route, ins, s, user_agent=service.user_agent(), sourceapp=service.SOURCEAPP))
        on = ins.get("online") or {}
        out["insight"] = {"status": on.get("status"), "seconds": round(time.time() - t, 1),
                          "prefix": bool(on.get("prefix")), "updates": bool((on.get("prefix") or {}).get("updates")),
                          "ris": bool((on.get("prefix") or {}).get("ris")), "baseline": on.get("baseline") is not None,
                          "as_path": ins.get("as_path_text")}
    out["calls"] = calls
    json.dump(out, sys.stdout, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "heise.de"))
