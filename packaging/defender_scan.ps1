# Scan built artifacts with Microsoft Defender on a Windows runner; fail on
# any detection.
#
#   pwsh packaging/defender_scan.ps1 -Report smoke\defender.txt <path> [<path> ...]
#
# - Signatures are updated first, and cloud-delivered protection is switched
#   on (lookups and ML verdicts, as on a normal Windows 11 PC; no samples are
#   sent), because an offline scan alone did not reproduce the detection that
#   deleted beta.3's one-file exe on a real PC.
# - An EICAR test file is scanned first: if Defender does not detect it, the
#   scanner is not working and the step fails rather than report "clean".
# - Each path (folder, zip or file) gets a custom scan with remediation off, so
#   a detection is reported, not silently deleted. Exit code 2 from MpCmdRun
#   means a threat was found.
param(
    [Parameter(Mandatory = $true)] [string] $Report,
    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)] [string[]] $Paths
)
$ErrorActionPreference = "Stop"
$mp = Join-Path $env:ProgramFiles "Windows Defender\MpCmdRun.exe"
$lines = New-Object System.Collections.Generic.List[string]
function Say([string] $text) { Write-Host $text; $lines.Add($text) }

& $mp -SignatureUpdate | Out-Host
Set-MpPreference -MAPSReporting Advanced -SubmitSamplesConsent NeverSend -CloudBlockLevel High -CloudExtendedTimeout 50
$status = Get-MpComputerStatus
Say ("Defender engine {0}, antivirus signatures {1} ({2}), service {3}, antivirus {4}" -f `
    $status.AMEngineVersion, $status.AntivirusSignatureVersion, $status.AntivirusSignatureLastUpdated, `
    $status.AMServiceEnabled, $status.AntivirusEnabled)
$pref = Get-MpPreference
Say ("Cloud protection: MAPSReporting {0}, CloudBlockLevel {1}, SubmitSamplesConsent {2}" -f `
    $pref.MAPSReporting, $pref.CloudBlockLevel, $pref.SubmitSamplesConsent)

$control = Join-Path $env:RUNNER_TEMP "eicar-control"
New-Item -ItemType Directory -Force $control | Out-Null
$eicar = 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
[IO.File]::WriteAllText((Join-Path $control "eicar.com"), $eicar)
& $mp -Scan -ScanType 3 -File $control -DisableRemediation | Out-Host
if ($LASTEXITCODE -ne 2) {
    Say "FAIL: Defender did not detect the EICAR test file (exit $LASTEXITCODE); the scan cannot be trusted."
    $lines | Set-Content -Encoding utf8 $Report
    exit 1
}
Say "Control: EICAR test file detected, the scanner works."

$failed = $false
foreach ($path in $Paths) {
    $full = (Resolve-Path $path).Path
    $output = & $mp -Scan -ScanType 3 -File $full -DisableRemediation 2>&1 | Out-String
    $code = $LASTEXITCODE
    Write-Host $output
    if ($code -eq 0) {
        Say "clean: $full"
    } elseif ($code -eq 2) {
        Say "DETECTED: $full"
        ($output -split "`n" | Where-Object { $_ -match "Threat|file\s+:" }) | ForEach-Object { Say ("    " + $_.Trim()) }
        $failed = $true
    } else {
        Say "ERROR: scanning $full returned $code"
        $failed = $true
    }
}
$lines | Set-Content -Encoding utf8 $Report
if ($failed) { exit 1 }
exit 0
