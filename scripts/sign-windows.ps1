# Signs a Windows release with the Certum code signing certificate (SimplySign),
# by hand on the maintainer's Windows machine. CI builds stay unsigned.
#
#   pwsh scripts/sign-windows.ps1 -Zip routemap-0.2.0-beta.2-windows-x86_64.zip `
#        -Setup routemap-0.2.0-beta.2-windows-x86_64-setup.exe -Thumbprint <SHA-1> [-Out signed]
#
# -Zip and -Setup are the unsigned files from the release (or the build run).
# Run it from a clone of this repository checked out at the release's commit,
# with SimplySign Desktop running and logged in (it presents the certificate in
# the current user's store), the Windows SDK's signtool.exe and Python 3.
#
# What it does, stopping at the first failure:
#   1. checks the certificate (in the store, code signing, not expired), the
#      clone's commit against the build's, and that the files are unsigned
#   2. signs routemap.exe and routemap-cli.exe (SHA-256, RFC 3161 timestamp)
#   3. rebuilds the installer around the signed folder with the same version,
#      commit and build number; Inno Setup signs Setup and its uninstaller
#   4. zips the signed folder under the release's zip name
#   5. verifies every signature (signtool verify /pa and Authenticode) and
#      prints the SHA-256 lines to put into SHA256SUMS before signing it with GPG
#
# Nothing is uploaded. Undo: delete the -Out folder.
param(
    [Parameter(Mandatory = $true)] [string] $Zip,
    [Parameter(Mandatory = $true)] [string] $Setup,
    [Parameter(Mandatory = $true)] [string] $Thumbprint,
    [string] $Out = "signed",
    [string] $TimestampUrl = "http://time.certum.pl",
    [string] $SignTool = ""
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
function Step($text) { Write-Host "`n== $text" }
function Fail($why) { Write-Host "FAILED: $why" -ForegroundColor Red; exit 1 }

# ---- 1. preconditions --------------------------------------------------------
Step "Checking the certificate, the tools and the files"
$Thumbprint = ($Thumbprint -replace "\s", "").ToUpper()
$cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Thumbprint -eq $Thumbprint }
if (-not $cert) { Fail "no certificate $Thumbprint in Cert:\CurrentUser\My (is SimplySign Desktop logged in?)" }
if (-not ($cert.EnhancedKeyUsageList | Where-Object { $_.ObjectId -eq "1.3.6.1.5.5.7.3.3" })) { Fail "certificate $Thumbprint is not for code signing" }
if ($cert.NotAfter -lt (Get-Date)) { Fail "certificate $Thumbprint expired on $($cert.NotAfter)" }
Write-Host "certificate: $($cert.Subject), valid until $($cert.NotAfter.ToString('yyyy-MM-dd'))"

if (-not $SignTool) {
    $SignTool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [version]($_.Directory.Parent.Name) } | Select-Object -Last 1 -ExpandProperty FullName
}
if (-not $SignTool -or -not (Test-Path $SignTool)) { Fail "signtool.exe not found; install the Windows SDK or pass -SignTool" }
Write-Host "signtool: $SignTool"

$Zip = (Resolve-Path $Zip).Path
$Setup = (Resolve-Path $Setup).Path
$zipName = Split-Path $Zip -Leaf
$setupName = Split-Path $Setup -Leaf
if ($zipName -notmatch '^routemap-(.+)-windows-x86_64\.zip$') { Fail "$zipName is not a release zip" }
$version = $Matches[1]
if ($setupName -notmatch "^routemap-$([regex]::Escape($version))(-([0-9a-f]{7}))?-windows-x86_64-setup\.exe$") {
    Fail "$setupName is not the installer for $version"
}
$short = $Matches[2]
$commitInName = [bool]$short
$runNumber = (Get-Item $Setup).VersionInfo.FileVersion.Split(".")[-1]
if (Test-Path $Out) { Fail "$Out already exists; move it away or pass another -Out" }
New-Item -ItemType Directory $Out | Out-Null
$Out = (Resolve-Path $Out).Path
$work = Join-Path $Out "work"
Expand-Archive $Zip -DestinationPath $work
$folder = Join-Path $work "Route Map"
$exes = @("routemap.exe", "routemap-cli.exe") | ForEach-Object { Join-Path $folder $_ }
foreach ($exe in $exes) {
    if (-not (Test-Path $exe)) { Fail "$exe is not in the zip" }
    if ((Get-AuthenticodeSignature $exe).Status -ne "NotSigned") { Fail "$exe is already signed" }
}
$v = & (Join-Path $folder "routemap-cli.exe") --version | Select-Object -First 1
if ("$v" -notmatch "commit ([0-9a-f]{12})") { Fail "routemap-cli.exe --version says '$v'" }
$commit12 = $Matches[1]
if ($short -and -not $commit12.StartsWith($short)) { Fail "the zip is commit $commit12, the installer $short" }
$head = (git -C $Root rev-parse HEAD).Trim()
if (-not $head.StartsWith($commit12)) { Fail "this clone is at $($head.Substring(0,12)); check out $commit12 so the installer script matches" }
Write-Host "release $version, commit $commit12, build $runNumber"

# ---- 2. sign the executables -------------------------------------------------
Step "Signing routemap.exe and routemap-cli.exe"
foreach ($exe in $exes) {
    & $SignTool sign /sha1 $Thumbprint /fd sha256 /tr $TimestampUrl /td sha256 /d "Route Map" $exe
    if ($LASTEXITCODE -ne 0) { Fail "signtool could not sign $exe" }
}

# ---- 3. the installer around the signed folder ---------------------------------
Step "Rebuilding the installer; Inno Setup signs Setup and its uninstaller"
$signCmd = "`$q$SignTool`$q sign /sha1 $Thumbprint /fd sha256 /tr $TimestampUrl /td sha256 /d `$qRoute Map`$q `$f"
$built = & pwsh (Join-Path $Root "packaging\windows\build_installer.ps1") -Source $folder -Version $version `
    -Commit $head -RunNumber $runNumber -Out $Out -SignCommand $signCmd -CommitInName:$commitInName | Select-Object -Last 1
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $built)) { Fail "the installer build failed" }
if ((Split-Path $built -Leaf) -ne $setupName) { Fail "the rebuilt installer is $(Split-Path $built -Leaf), expected $setupName" }

# ---- 4. the zip ----------------------------------------------------------------
Step "Zipping the signed folder"
$signedZip = Join-Path $Out $zipName
Compress-Archive -Path $folder -DestinationPath $signedZip

# ---- 5. verify -----------------------------------------------------------------
Step "Verifying every signature"
$check = Join-Path $Out "check"
Expand-Archive $signedZip -DestinationPath $check
$targets = @($built) + (@("routemap.exe", "routemap-cli.exe") | ForEach-Object { Join-Path $check "Route Map\$_" })
foreach ($f in $targets) {
    & $SignTool verify /pa /tw $f | Out-Null
    if ($LASTEXITCODE -ne 0) { & $SignTool verify /pa /v $f; Fail "signtool verify failed for $f" }
    $sig = Get-AuthenticodeSignature $f
    if ($sig.Status -ne "Valid") { Fail "$f : Authenticode status $($sig.Status)" }
    if ($sig.SignerCertificate.Thumbprint -ne $Thumbprint) { Fail "$f is signed by $($sig.SignerCertificate.Thumbprint)" }
    if (-not $sig.TimeStamperCertificate) { Fail "$f has no timestamp" }
    Write-Host "ok: $(Split-Path $f -Leaf) signed by $($sig.SignerCertificate.Subject), timestamped"
}
Remove-Item -Recurse $work, $check

Step "SHA-256 for SHA256SUMS (replace the unsigned files' lines, then sign SHA256SUMS with GPG)"
foreach ($f in @($built, $signedZip)) {
    "{0}  {1}" -f (Get-FileHash $f -Algorithm SHA256).Hash.ToLower(), (Split-Path $f -Leaf)
}
Write-Host "`nSigned files are in $Out. Upload them over the unsigned ones on the release, with the new SHA256SUMS and SHA256SUMS.asc."
