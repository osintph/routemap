# Builds the Windows installer around a "Route Map" folder (routemap.exe,
# routemap-cli.exe and their files). Used by build.yml, installers.yml and
# scripts/sign-windows.ps1, so the installer is built the same way everywhere.
#
#   pwsh packaging/windows/build_installer.ps1 -Source "build\nuitka\windows\Route Map" `
#        -Commit <sha> -RunNumber <n> -Out out
#
# The version is the app's own (routemap.__about__.VERSION) unless -Version is
# given. Inno Setup 6.7.3 is downloaded once, checked against its pinned
# SHA-256 and installed for the current user under %LOCALAPPDATA%\RouteMapBuild.
# Prints the installer's path.
param(
    [Parameter(Mandatory = $true)] [string] $Source,
    [Parameter(Mandatory = $true)] [string] $Commit,
    [Parameter(Mandatory = $true)] [string] $RunNumber,
    [Parameter(Mandatory = $true)] [string] $Out,
    [string] $Version = "",
    # A signtool command line with $f for the file (scripts/sign-windows.ps1);
    # empty for an unsigned installer.
    [string] $SignCommand = "",
    # installers.yml: put the commit in the file name (test builds of any run).
    [switch] $CommitInName
)
$ErrorActionPreference = "Stop"
$InnoUrl = "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe"
$InnoSha256 = "9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")

function Find-Iscc {
    # Only the pinned copy (or one named in $env:ISCC): another Inno Setup
    # version on the machine would build a different installer.
    $candidates = @($env:ISCC, (Join-Path $env:LOCALAPPDATA "RouteMapBuild\inno-6.7.3\ISCC.exe"))
    foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { return $c } }
    $dir = Join-Path $env:LOCALAPPDATA "RouteMapBuild\inno-6.7.3"
    $exe = Join-Path ([IO.Path]::GetTempPath()) "innosetup-6.7.3.exe"
    Write-Host "downloading Inno Setup 6.7.3"
    Invoke-WebRequest -Uri $InnoUrl -OutFile $exe
    $hash = (Get-FileHash $exe -Algorithm SHA256).Hash
    if ($hash -ne $InnoSha256) { throw "Inno Setup checksum $hash does not match the pinned $InnoSha256" }
    $p = Start-Process $exe -PassThru -Wait -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CURRENTUSER", "/DIR=$dir")
    if ($p.ExitCode -ne 0) { throw "Inno Setup install exited $($p.ExitCode)" }
    return (Join-Path $dir "ISCC.exe")
}

function Find-Python {
    foreach ($c in @(@("python"), @("py", "-3"))) {
        if (Get-Command $c[0] -ErrorAction SilentlyContinue) { return $c }
    }
    throw "Python 3 is needed to read the names from routemap/__about__.py (winget install Python.Python.3.12)"
}
$py = Find-Python
$pyArgs = @($py | Select-Object -Skip 1)

if (-not $Version) {
    $Version = & $py[0] @pyArgs -c "import sys; sys.path.insert(0, r'$Root'); from routemap.__about__ import VERSION; print(VERSION)"
}
$Source = (Resolve-Path $Source).Path
New-Item -ItemType Directory -Force $Out | Out-Null
$Out = (Resolve-Path $Out).Path
foreach ($exe in "routemap.exe", "routemap-cli.exe") {
    if (-not (Test-Path (Join-Path $Source $exe))) { throw "$exe is not in $Source" }
}
$iscc = Find-Iscc
$nameArgs = @(); if ($CommitInName) { $nameArgs = @("--commit-in-name") }
$defs = & $py[0] @pyArgs (Join-Path $Root "packaging\windows\iss_defines.py") $Version $Commit $RunNumber $Source $Out @nameArgs
if ($SignCommand) { $defs += @("/DSign=1", "/Ssigntool=$SignCommand") }
& $iscc /Qp @defs (Join-Path $Root "packaging\windows\routemap.iss") | Out-Host
if ($LASTEXITCODE -ne 0) { throw "ISCC exited $LASTEXITCODE" }
$setup = Get-ChildItem $Out -Filter "*-setup.exe" | Sort-Object LastWriteTime | Select-Object -Last 1
$setup.FullName
