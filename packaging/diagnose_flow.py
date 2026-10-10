"""Windows flow-field check for path discovery (0.4.0, D3).

    python packaging/diagnose_flow.py > flow.json      (administrator: pktmon)

Paris-style path discovery needs every probe of one flow to carry the same
flow fields. This records what Windows actually puts on the wire:

* IcmpSendEcho: the identifier, sequence number and checksum of each echo
  request (the API has no parameter for any of them).
* A TCP connect with TCP_FAIL_CONNECT_ON_ICMP_ERROR (Windows 10 2004+): the
  source port, TTL and sequence of each SYN, and what TCP_ICMP_ERROR_INFO
  reports when a router answers with time exceeded.

Packets are captured with pktmon and read from its pcapng. Contacts only
1.1.1.1 (ICMP echo and TCP 443), at TTL 1 to 3.
"""
from __future__ import annotations

import ctypes
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time

TARGET = "1.1.1.1"
PAYLOAD = b"routemap-flow-check" + b"\0" * 13


def run(argv):
    p = subprocess.run(argv, capture_output=True, text=True, errors="replace")
    return {"argv": argv, "code": p.returncode, "out": p.stdout[-800:], "err": p.stderr[-400:]}


def icmp_probes(out):
    from routemap_engine import probe
    ct, lib, Options, Reply = probe._windows_api()
    sent = []
    for ttl in (1, 2, 3):
        for _ in range(3):
            handle = lib.IcmpCreateFile()
            options = Options(Ttl=ttl)
            req = ct.create_string_buffer(PAYLOAD, len(PAYLOAD))
            size = ct.sizeof(Reply) + len(PAYLOAD) + 8 + 64
            rep = ct.create_string_buffer(size)
            dest = struct.unpack("<I", socket.inet_aton(TARGET))[0]
            n = lib.IcmpSendEcho(handle, dest, req, len(PAYLOAD), ct.byref(options), rep, size, 1000)
            status = Reply.from_buffer_copy(rep.raw[:ct.sizeof(Reply)]).Status if n else None
            sent.append({"ttl": ttl, "replies": n, "status": status})
            lib.IcmpCloseHandle(handle)
    out["icmp_calls"] = sent


class SOCKADDR_INET(ctypes.Union):
    _fields_ = [("raw", ctypes.c_ubyte * 28)]


class ICMP_ERROR_INFO(ctypes.Structure):
    _fields_ = [("srcaddress", SOCKADDR_INET), ("protocol", ctypes.c_int),
                ("type", ctypes.c_ubyte), ("code", ctypes.c_ubyte)]


# ws2ipdef.h; WSASetFailConnectOnIcmpError and WSAGetIcmpErrorInfo are inline
# wrappers around these options, not exports of ws2_32.dll (run 38033956629).
TCP_NOSYNRETRIES = 9
TCP_FAIL_CONNECT_ON_ICMP_ERROR = 18
TCP_ICMP_ERROR_INFO = 19


def tcp_probes(out):
    ws2 = ctypes.WinDLL("ws2_32.dll", use_last_error=True)
    ws2.getsockopt.argtypes = [ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                               ctypes.POINTER(ctypes.c_int)]
    results = []
    for port in (33001, 33001, 33002):
        for ttl in (1, 2, 3):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            row = {"sport": port, "ttl": ttl}
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", port))
                s.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
                for name, opt in (("nosynretries", TCP_NOSYNRETRIES), ("fail_on_icmp", TCP_FAIL_CONNECT_ON_ICMP_ERROR)):
                    try:
                        s.setsockopt(socket.IPPROTO_TCP, opt, 1)
                        row[name] = "set"
                    except OSError as exc:
                        row[name] = f"refused winerror={getattr(exc, 'winerror', None)}"
                s.settimeout(3)
                t = time.perf_counter()
                try:
                    s.connect((TARGET, 443))
                    row["connect"] = "connected"
                except OSError as exc:
                    row["connect"] = f"{type(exc).__name__} winerror={getattr(exc, 'winerror', None)}"
                row["ms"] = round((time.perf_counter() - t) * 1000, 1)
                info = ICMP_ERROR_INFO()
                size = ctypes.c_int(ctypes.sizeof(info))
                rc = ws2.getsockopt(s.fileno(), socket.IPPROTO_TCP, TCP_ICMP_ERROR_INFO, ctypes.byref(info),
                                    ctypes.byref(size))
                row["info_rc"], row["info_len"] = rc, size.value
                row["info_err"] = ctypes.get_last_error() if rc else 0
                if rc == 0 and size.value:
                    raw = bytes(info.srcaddress.raw)
                    fam = struct.unpack("<H", raw[:2])[0]
                    row["icmp"] = {"family": fam, "src": socket.inet_ntoa(raw[4:8]) if fam == 2 else raw.hex(),
                                   "protocol": info.protocol, "type": info.type, "code": info.code}
            except OSError as exc:
                row["error"] = repr(exc)
            finally:
                s.close()
            results.append(row)
    out["tcp_calls"] = results


def pcapng_packets(path):
    data = open(path, "rb").read()
    i, little = 0, True
    while i + 12 <= len(data):
        btype, blen = struct.unpack_from("<II", data, i)
        if blen < 12:
            break
        if btype == 6:  # enhanced packet block
            caplen = struct.unpack_from("<I", data, i + 20)[0]
            yield data[i + 28:i + 28 + caplen]
        i += blen


def decode(frame):
    # Ethernet, maybe one VLAN tag; IPv4 only here.
    off = 12
    etype = struct.unpack_from("!H", frame, off)[0]
    off += 2
    if etype == 0x8100:
        etype = struct.unpack_from("!H", frame, off + 2)[0]
        off += 4
    if etype != 0x0800:
        return None
    ip = frame[off:]
    ihl = (ip[0] & 15) * 4
    ttl, proto = ip[8], ip[9]
    src, dst = socket.inet_ntoa(ip[12:16]), socket.inet_ntoa(ip[16:20])
    l4 = ip[ihl:]
    if proto == 1 and dst == TARGET and l4[0] == 8:
        _t, _c, csum, ident, seq = struct.unpack_from("!BBHHH", l4)
        return {"kind": "echo", "ttl": ttl, "id": ident, "seq": seq, "csum": csum}
    if proto == 6 and dst == TARGET:
        sport, dport, seq = struct.unpack_from("!HHI", l4)
        flags = l4[13]
        if flags & 0x02:
            return {"kind": "syn", "ttl": ttl, "sport": sport, "dport": dport, "seq": seq}
    if proto == 1 and l4[0] in (11, 3):
        return {"kind": f"icmp{l4[0]}", "from": "router"}
    return None


def main():
    out = {"python": sys.version.split()[0], "windows": sys.getwindowsversion()._asdict()
           if hasattr(sys.getwindowsversion(), "_asdict") else str(sys.getwindowsversion())}
    work = tempfile.mkdtemp()
    etl, pcap = os.path.join(work, "flow.etl"), os.path.join(work, "flow.pcapng")
    out["pktmon"] = [run(["pktmon", "filter", "remove"]),
                     run(["pktmon", "filter", "add", "-i", TARGET]),
                     run(["pktmon", "start", "--capture", "--pkt-size", "0", "--file-name", etl])]
    try:
        icmp_probes(out)
        tcp_probes(out)
    finally:
        time.sleep(1)
        out["pktmon"].append(run(["pktmon", "stop"]))
        out["pktmon"].append(run(["pktmon", "etl2pcap", etl, "--out", pcap]))
    seen, packets = set(), []
    if os.path.exists(pcap):
        for frame in pcapng_packets(pcap):
            try:
                d = decode(frame)
            except (IndexError, struct.error):
                d = None
            if d is not None:
                key = json.dumps(d, sort_keys=True)
                if key not in seen:        # pktmon logs each packet at several components
                    seen.add(key)
                    packets.append(d)
    out["wire"] = packets
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
