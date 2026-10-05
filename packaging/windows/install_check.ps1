# Installs, checks and uninstalls the Windows installer, in both modes.
#
#   pwsh packaging/windows/install_check.ps1 -Setup <setup.exe> -Commit <sha>
#
# Per user (/CURRENTUSER, no admin rights used) and per machine (/ALLUSERS):
# the files land in the right folder, both executables are there and report the
# commit, the Start menu shortcut and the Settings > Apps entry exist, the PATH
# task adds the bin folder (only the CLI launcher in it, never the app folder)
# once; per machine a /DIR= elsewhere is ignored and Program Files is used;
# installing again over it (an upgrade) leaves one entry; the uninstaller
# removes the folder, the shortcut, the entry and the PATH change. Exits
# non-zero on the first failure.
param(
    [Parameter(Mandatory = $true)] [string] $Setup,
    [Parameter(Mandatory = $true)] [string] $Commit,
    [string] $AppName = "Route Map",
    [string] $Name = "routemap",
    # An earlier release's installer: installed per machine into a chosen folder
    # (0.2.0-beta.2 allowed that), then upgraded; the folder and its PATH entry
    # must be gone afterwards.
    [string] $PreviousSetup = ""
)
$ErrorActionPreference = "Stop"
$Guid = "{260F97E1-3DC2-4D4E-9070-C4D930805B2E}_is1"

function Fail($why) { Write-Host "::error::$why"; exit 1 }
function Check($ok, $why) { if (-not $ok) { Fail $why } else { Write-Host "ok: $why" } }

function Run-Setup($mode, $log, $extra = @()) {
    $p = Start-Process -FilePath $Setup -PassThru -Wait -ArgumentList (@(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", $mode, "/TASKS=addtopath", "/LOG=$log") + $extra)
    if ($p.ExitCode -ne 0) { Get-Content $log | Select-Object -Last 40; Fail "setup $mode exited $($p.ExitCode)" }
}

function Path-Entries($scope) {
    $raw = [Environment]::GetEnvironmentVariable("Path", $scope)
    @($raw -split ";" | Where-Object { $_ -ne "" })
}

function Check-Path($scope, $bin, $dir, $why) {
    Check ((Path-Entries $scope | Where-Object { $_ -ieq $bin }).Count -eq 1) "PATH ($scope) has the bin folder once$why"
    Check ((Path-Entries $scope | Where-Object { $_ -ieq $dir }).Count -eq 0) "PATH ($scope) does not have the app folder$why"
}

function Check-Mode($mode, $root, $dir, $menu, $scope, $extra = @()) {
    Write-Host "---- $mode $extra"
    Run-Setup $mode "$env:RUNNER_TEMP\setup-$($mode.Trim('/')).log" $extra
    $bin = Join-Path $dir "bin"
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
    Check-Path $scope $bin $dir ""
    $inBin = @(Get-ChildItem $bin -Force | ForEach-Object { $_.Name })
    Check (($inBin.Count -eq 1) -and ($inBin[0] -eq "$Name-cli.cmd")) "the bin folder holds only $Name-cli.cmd ($($inBin -join ', '))"
    $v = & (Join-Path $bin "$Name-cli.cmd") --version
    Check ("$v" -match "commit $($Commit.Substring(0,12))") "the launcher runs the installed CLI ($v)"

    Run-Setup $mode "$env:RUNNER_TEMP\upgrade-$($mode.Trim('/')).log"
    Check ((Get-ChildItem "${root}:\Software\Microsoft\Windows\CurrentVersion\Uninstall" | Where-Object { $_.PSChildName -eq $Guid }).Count -eq 1) "installing over it keeps one entry"
    Check-Path $scope $bin $dir " after the upgrade"
    Check (Test-Path $cli) "and the files are there"

    $uninstall = (Get-ItemProperty $key).UninstallString.Trim('"')
    $ulog = "$env:RUNNER_TEMP\uninstall-$($mode.Trim('/')).log"
    $p = Start-Process -FilePath $uninstall -PassThru -Wait -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=$ulog")
    Check ($p.ExitCode -eq 0) "uninstaller exited 0"
    # Inno's uninstaller relaunches itself from %TEMP% (_iu*.tmp) and removes the
    # files from there; wait for that copy to exit before looking.
    for ($i = 0; $i -lt 120; $i++) {
        $copy = Get-Process | Where-Object { $_.Path -and (Split-Path $_.Path -Leaf) -like "_iu*.tmp" }
        if (-not $copy) { break }
        Start-Sleep -Seconds 1
    }
    for ($i = 0; $i -lt 30 -and (Test-Path $dir); $i++) { Start-Sleep -Seconds 1 }
    $left = @(if (Test-Path $dir) { Get-ChildItem $dir -Recurse -Force -File })
    if ($left.Count -gt 0) {
        Write-Host "left behind:"; $left | ForEach-Object { Write-Host "  $($_.FullName)" }
        if (Test-Path $ulog) { Get-Content $ulog | Select-Object -Last 40 }
        Fail "the uninstaller left $($left.Count) file(s) in $dir"
    }
    if (Test-Path $dir) { Write-Host "::warning::$dir is empty but still there" } else { Write-Host "ok: $dir removed" }
    Check (-not (Test-Path $key)) "Settings > Apps entry removed"
    Check (-not (Test-Path (Join-Path $menu "$AppName.lnk"))) "Start menu shortcut removed"
    Check ((Path-Entries $scope | Where-Object { $_ -ieq $bin -or $_ -ieq $dir }).Count -eq 0) "PATH ($scope) no longer has the bin folder"
}

Check-Mode "/CURRENTUSER" "HKCU" (Join-Path $env:LOCALAPPDATA "Programs\$AppName") `
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs") "User"
$elsewhere = "C:\RouteMapElsewhere"
Check-Mode "/ALLUSERS" "HKLM" (Join-Path $env:ProgramFiles $AppName) `
    (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs") "Machine" @("/DIR=$elsewhere")
Check (-not (Test-Path $elsewhere)) "a per-machine install ignored /DIR=$elsewhere"

if ($PreviousSetup) {
    Write-Host "---- upgrade from a per-machine install in a chosen folder"
    $old = "C:\RouteMapOld"
    $p = Start-Process -FilePath $PreviousSetup -PassThru -Wait -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/ALLUSERS", "/TASKS=addtopath", "/DIR=$old",
        "/LOG=$env:RUNNER_TEMP\previous.log")
    Check ($p.ExitCode -eq 0) "the earlier release installed (exit $($p.ExitCode))"
    Check (Test-Path (Join-Path $old "$Name.exe")) "the earlier release is in $old"
    Check ((Path-Entries "Machine" | Where-Object { $_ -ieq $old }).Count -eq 1) "and $old is on the machine PATH"
    Run-Setup "/ALLUSERS" "$env:RUNNER_TEMP\upgrade-from-previous.log"
    $dir = Join-Path $env:ProgramFiles $AppName
    $bin = Join-Path $dir "bin"
    Check (Test-Path (Join-Path $dir "$Name.exe")) "the new release is in $dir"
    $left = @(if (Test-Path $old) { Get-ChildItem $old -Recurse -Force | ForEach-Object { $_.FullName } })
    if ($left.Count -gt 0) { Write-Host "left in ${old}:"; $left | Select-Object -First 20 | ForEach-Object { Write-Host "  $_" } }
    Check (-not (Test-Path $old)) "the earlier folder $old is gone"
    Check ((Path-Entries "Machine" | Where-Object { $_ -ieq $old -or $_ -ieq "$old\bin" }).Count -eq 0) "the machine PATH no longer has $old"
    Check ((Path-Entries "Machine" | Where-Object { $_ -ieq $bin }).Count -eq 1) "and has $bin once"
    $key = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$Guid"
    Check ((Get-ItemProperty $key).UninstallString.Trim('"') -like "$dir\*") "Settings > Apps now uninstalls from $dir"
    $p = Start-Process -FilePath (Get-ItemProperty $key).UninstallString.Trim('"') -PassThru -Wait `
        -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
    Check ($p.ExitCode -eq 0) "and that uninstaller exited 0"
}
Write-Host "all installer checks passed"
