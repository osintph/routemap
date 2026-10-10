# Route Map 0.4.0, D3: can Windows hold a flow for path discovery without
# administrator rights, using TCP connects?
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File flowcheck_tcp.ps1 [target] [port]
#
# For TTL 1 to 20 it opens a TCP connection to the target (default
# heise.de:443) with the TTL set, a fixed source port (the flow) and no SYN
# retries, with TCP_FAIL_CONNECT_ON_ICMP_ERROR on (Windows 10 2004 or later).
# When a router answers "time exceeded", connect fails and
# TCP_ICMP_ERROR_INFO names that router. Each TTL is probed with flow A twice
# and flow B once. One probe at a time, at most 3 a second; about 30 to 60
# seconds in all. No administrator rights, nothing installed, nothing written
# except this output. A probe that reaches the target is a normal TCP
# connection, closed at once.
#
# PASS: at least 3 hops before the target answered through
# TCP_ICMP_ERROR_INFO with a router address and an ICMP time exceeded
# (type 11 over IPv4, type 3 over IPv6). FAIL otherwise, with the reason.
param([string]$Target = "heise.de", [int]$Port = 443, [int]$MaxTtl = 20)
$ErrorActionPreference = "Stop"

$source = @"
using System;
using System.Net;
using System.Net.Sockets;
using System.Diagnostics;

public static class RouteMapFlowCheck {
    // ws2ipdef.h
    const int TCP_NOSYNRETRIES = 9;
    const int TCP_FAIL_CONNECT_ON_ICMP_ERROR = 18;
    const int TCP_ICMP_ERROR_INFO = 19;

    public static string Probe(IPAddress dst, int port, int ttl, int sport, int waitMs) {
        bool v6 = dst.AddressFamily == AddressFamily.InterNetworkV6;
        Socket s = new Socket(dst.AddressFamily, SocketType.Stream, ProtocolType.Tcp);
        try {
            s.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
            s.Bind(new IPEndPoint(v6 ? IPAddress.IPv6Any : IPAddress.Any, sport));
            if (v6) s.SetSocketOption(SocketOptionLevel.IPv6, SocketOptionName.HopLimit, ttl);
            else s.Ttl = (short)ttl;
            s.SetSocketOption(SocketOptionLevel.Tcp, (SocketOptionName)TCP_NOSYNRETRIES, 1);
            try {
                s.SetSocketOption(SocketOptionLevel.Tcp, (SocketOptionName)TCP_FAIL_CONNECT_ON_ICMP_ERROR, 1);
            } catch (SocketException e) {
                return "option-refused winerror=" + e.ErrorCode;
            }
            Stopwatch sw = Stopwatch.StartNew();
            IAsyncResult ar = s.BeginConnect(new IPEndPoint(dst, port), null, null);
            if (!ar.AsyncWaitHandle.WaitOne(waitMs)) return "timeout";
            double ms;
            try {
                s.EndConnect(ar);
                ms = sw.Elapsed.TotalMilliseconds;
                return "reached connected " + ms.ToString("F1") + " ms";
            } catch (SocketException e) {
                ms = sw.Elapsed.TotalMilliseconds;
                if (e.ErrorCode == 10061) return "reached refused " + ms.ToString("F1") + " ms";
                byte[] info;
                try {
                    info = s.GetSocketOption(SocketOptionLevel.Tcp, (SocketOptionName)TCP_ICMP_ERROR_INFO, 64);
                } catch (SocketException e2) {
                    return "error winerror=" + e.ErrorCode + " info-refused winerror=" + e2.ErrorCode + " " + ms.ToString("F1") + " ms";
                }
                if (info == null || info.Length < 34) return "error winerror=" + e.ErrorCode + " no-icmp-info " + ms.ToString("F1") + " ms";
                int family = BitConverter.ToUInt16(info, 0);
                string addr;
                if (family == 2) {
                    addr = new IPAddress(new byte[] { info[4], info[5], info[6], info[7] }).ToString();
                } else if (family == 23) {
                    byte[] a = new byte[16];
                    Array.Copy(info, 8, a, 0, 16);
                    addr = new IPAddress(a).ToString();
                } else {
                    addr = "family" + family;
                }
                int type = info[32], code = info[33];
                return "router " + addr + " type " + type + " code " + code + " " + ms.ToString("F1") + " ms winerror=" + e.ErrorCode;
            }
        } finally {
            try { s.LingerState = new LingerOption(true, 0); } catch (Exception) { }
            s.Close();
        }
    }
}
"@
Add-Type -TypeDefinition $source -Language CSharp

$os = [System.Environment]::OSVersion.Version
$build = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion").CurrentBuild
Write-Output "Route Map D3 TCP flow check, PowerShell $($PSVersionTable.PSVersion), Windows $($os.Major).$($os.Minor) build $build"
$dst = [System.Net.Dns]::GetHostAddresses($Target) | Where-Object { $_.AddressFamily -eq "InterNetwork" } | Select-Object -First 1
if (-not $dst) { $dst = [System.Net.Dns]::GetHostAddresses($Target) | Select-Object -First 1 }
Write-Output "Target $Target ($dst) port $Port; flow A = source port 33461, flow B = 33462"

$answered = 0
$reachedAt = $null
$problems = @()
for ($ttl = 1; $ttl -le $MaxTtl; $ttl++) {
    $a1 = [RouteMapFlowCheck]::Probe($dst, $Port, $ttl, 33461, 2000); Start-Sleep -Milliseconds 350
    $a2 = [RouteMapFlowCheck]::Probe($dst, $Port, $ttl, 33461, 2000); Start-Sleep -Milliseconds 350
    $b1 = [RouteMapFlowCheck]::Probe($dst, $Port, $ttl, 33462, 2000); Start-Sleep -Milliseconds 350
    Write-Output ("{0,2}  A: {1}" -f $ttl, $a1)
    Write-Output ("    A: {0}" -f $a2)
    Write-Output ("    B: {0}" -f $b1)
    foreach ($r in @($a1, $a2, $b1)) {
        if ($r -like "option-refused*") { $problems += "TCP_FAIL_CONNECT_ON_ICMP_ERROR was refused ($r)" }
    }
    $timeExceeded = @($a1, $a2, $b1) | Where-Object { $_ -match "^router \S+ type (11|3) " }
    if ($timeExceeded) { $answered++ }
    if (@($a1, $a2, $b1) | Where-Object { $_ -like "reached*" }) { $reachedAt = $ttl; break }
    if ($problems) { break }
}
Write-Output ""
if ($problems) {
    Write-Output "RESULT: FAIL: $($problems | Select-Object -First 1)"
} elseif ($answered -ge 3) {
    $tail = if ($reachedAt) { "; target reached at TTL $reachedAt" } else { "; target not reached within $MaxTtl" }
    Write-Output ("RESULT: PASS: $answered hops answered through TCP_ICMP_ERROR_INFO" + $tail)
} else {
    Write-Output "RESULT: FAIL: only $answered hops answered through TCP_ICMP_ERROR_INFO (3 needed)"
}
