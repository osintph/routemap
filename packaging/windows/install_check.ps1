# Installs, checks and uninstalls the Windows installer, in both modes.
#
#   pwsh packaging/windows/install_check.ps1 -Setup <setup.exe> -Commit <sha>
#
# Per user (/CURRENTUSER, no admin rights used) and per machine (/ALLUSERS):
# the files land in the right folder, both executables are there and report the
# commit, the Start menu shortcut and the Settings > Apps entry exist, the PATH
# task adds the folder once; installing again over it (an upgrade) leaves one
# entry; the uninstaller removes the folder, the shortcut, the entry and the
# PATH change. Exits non-zero on the first failure.
param(
    [Parameter(Mandatory = $true)] [string] $Setup,
    [Parameter(Mandatory = $true)] [string] $Commit,
    [string] $AppName = "Route Map",
    [string] $Name = "routemap"
)
$ErrorActionPreference = "Stop"
$Guid = "{260F97E1-3DC2-4D4E-9070-C4D930805B2E}_is1"

function Fail($why) { Write-Host "::error::$why"; exit 1 }
function Check($ok, $why) { if (-not $ok) { Fail $why } else { Write-Host "ok: $why" } }

function Run-Setup($mode, $log) {
    $p = Start-Process -FilePath $Setup -PassThru -Wait -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", $mode, "/TASKS=addtopath", "/LOG=$log")
    if ($p.ExitCode -ne 0) { Get-Content $log | Select-Object -Last 40; Fail "setup $mode exited $($p.ExitCode)" }
}

function Path-Entries($scope) {
    $raw = [Environment]::GetEnvironmentVariable("Path", $scope)
    @($raw -split ";" | Where-Object { $_ -ne "" })
}

function Check-Mode($mode, $root, $dir, $menu, $scope) {
    Write-Host "---- $mode"
    Run-Setup $mode "$env:RUNNER_TEMP\setup-$($mode.Trim('/')).log"
    $gui = Join-Path $dir "$Name.exe"
    $cli = Join-Path $dir "$Name-cli.exe"
    Check (Test-Path $gui) "$gui installed"
    Check (Test-Path $cli) "$cli installed next to it"
    $v = & $cli --version
    Check ("$v" -match "commit $($Commit.Substring(0,12))") "the installed CLI reports commit $($Commit.Substring(0,12)) ($v)"
    python packaging/verify_windows.py $gui $cli
    Check ($LASTEXITCODE -eq 0) "installed executables: windowed app without a console, console CLI"
    Check (Test-Path (Join-Path $menu "$AppName.lnk")) "Start menu shortcut in $menu"
    $key = "${root}:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$Guid"
    Check (Test-Path $key) "Settings > Apps entry under $root"
    $entry = Get-ItemProperty $key
    Check ($entry.DisplayName -eq $AppName) "listed as '$($entry.DisplayName)', version $($entry.DisplayVersion), publisher $($entry.Publisher)"
    Check ((Path-Entries $scope | Where-Object { $_ -ieq $dir }).Count -eq 1) "PATH ($scope) has the folder once"

    Run-Setup $mode "$env:RUNNER_TEMP\upgrade-$($mode.Trim('/')).log"
    Check ((Get-ChildItem "${root}:\Software\Microsoft\Windows\CurrentVersion\Uninstall" | Where-Object { $_.PSChildName -eq $Guid }).Count -eq 1) "installing over it keeps one entry"
    Check ((Path-Entries $scope | Where-Object { $_ -ieq $dir }).Count -eq 1) "and PATH still has the folder once"
    Check (Test-Path $cli) "and the files are there"

    $uninstall = (Get-ItemProperty $key).UninstallString.Trim('"')
    $ulog = "$env:RUNNER_TEMP\uninstall-$($mode.Trim('/')).log"
    $p = Start-Process -FilePath $uninstall -PassThru -Wait -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=$ulog")
    Check ($p.ExitCode -eq 0) "uninstaller exited 0"
    # The uninstaller finishes from a copy of itself; give it time to remove the folder.
    for ($i = 0; $i -lt 60 -and (Test-Path $dir); $i++) { Start-Sleep -Seconds 1 }
    if (Test-Path $dir) {
        Write-Host "left behind:"; Get-ChildItem $dir -Recurse -Force | ForEach-Object { Write-Host "  $($_.FullName)" }
        Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($dir) } | ForEach-Object { Write-Host "  running: $($_.Id) $($_.Path)" }
        if (Test-Path $ulog) { Get-Content $ulog | Select-Object -Last 40 }
    }
    Check (-not (Test-Path $dir)) "$dir removed"
    Check (-not (Test-Path $key)) "Settings > Apps entry removed"
    Check (-not (Test-Path (Join-Path $menu "$AppName.lnk"))) "Start menu shortcut removed"
    Check ((Path-Entries $scope | Where-Object { $_ -ieq $dir }).Count -eq 0) "PATH ($scope) no longer has the folder"
}

Check-Mode "/CURRENTUSER" "HKCU" (Join-Path $env:LOCALAPPDATA "Programs\$AppName") `
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs") "User"
Check-Mode "/ALLUSERS" "HKLM" (Join-Path $env:ProgramFiles $AppName) `
    (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs") "Machine"
Write-Host "all installer checks passed"
