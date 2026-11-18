param(
    [Parameter(Mandatory=$true)][string]$Apk,
    [ValidateSet('Shipping','Development')][string]$Configuration='Shipping',
    [string]$BuildEvidence='',
    [switch]$KeepInstalled
)
# Launch / menu / save / reload / Continue / Quit smoke of a Quest 3 APK built by BuildReleaseAndroidQuest3.ps1,
# driven only through adb (fresh app data, key events the story manager polls as keyboard keys, screencap
# screenshots, logcat). Writes output/quest3_device/<stamp>/smoke.json + screenshots + logcat.txt. Every step
# records what adb returned; a step that could not be observed is recorded as not observed, never as passed.
$ErrorActionPreference='Stop'
$releaseRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if ((Split-Path -Leaf $releaseRoot) -ne 'Release_20261026') { throw 'Device smoke runs only from the Release copy.' }
. (Join-Path $PSScriptRoot 'Quest3Device.ps1')
$apkFile=Get-Item -LiteralPath $Apk
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmss')
$evidence=Join-Path $releaseRoot ('output/quest3_device/'+$stamp)
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$shots=Join-Path $evidence 'screenshots'
$report=[ordered]@{ run=$stamp; utc=[DateTime]::UtcNow.ToString('o'); apk=$apkFile.FullName; apk_sha256=(Get-FileHash -LiteralPath $apkFile.FullName -Algorithm SHA256).Hash.ToLower(); apk_bytes=$apkFile.Length;
    configuration=$Configuration; build_evidence=$BuildEvidence; package=$Quest3Package; steps=@(); screenshots=@(); success=$false;
    scope='adb-driven install, launch, menu, New Game, skip, pause, save, load, main menu, Continue, Quit on the connected Quest 3; keyboard key events only; no controller, comfort or frame-time claim' }
$steps=[System.Collections.ArrayList]::new()
function Step([string]$name,[scriptblock]$body) {
    $row=[ordered]@{ step=$name; utc=[DateTime]::UtcNow.ToString('o'); ok=$false }
    try { $result=& $body; $row.result=$result; $row.ok=$true }
    catch { $row.error=$_.Exception.Message }
    [void]$steps.Add($row)
    $report.steps=@($steps)
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidence 'smoke.json') -Encoding utf8
    if (-not $row.ok) { throw ('Step failed: '+$name+' - '+$row.error) }
    return $result
}
function Shot([string]$name) { $s=Quest3-Screenshot $shots $name; $report.screenshots=@($report.screenshots)+@($s); return $s }
$logcat=$null
try {
    $device=Step 'device present and authorized' { Quest3-RequireDevice }
    $report.device=$device
    $report.device_properties=Step 'device properties' { Quest3-Props }
    $report.installed_before=Step 'package state before' { [ordered]@{ installed=(Quest3-Installed); version=$(if (Quest3-Installed) { Quest3-PackageVersion } else { $null }) } }
    Step 'fresh app data: force-stop and uninstall any previous package' {
        Quest3-Adb shell am force-stop $Quest3Package | Out-Null
        if (Quest3-Installed) { return (Quest3-Adb uninstall $Quest3Package).text } else { return 'not installed' }
    } | Out-Null
    Step 'install APK' { $r=Quest3-Adb install -r -g $apkFile.FullName; if ($r.text -notmatch 'Success') { throw ('adb install: '+$r.text) }; return $r.text }
    $report.installed_version=Step 'installed package version' { if (-not (Quest3-Installed)) { throw 'package not present after install' }; Quest3-PackageVersion }
    Step 'proximity override on (runtime treats the headset as worn)' { Quest3-ProximityOverride $true } | Out-Null
    $logFile=Join-Path $evidence 'logcat.txt'
    $logcat=Quest3-StartLogcat $logFile
    $launch=Step 'launch (cold start, fresh data)' { Quest3-Launch }
    $report.cold_start=Step 'engine initialised and startup map loaded (logcat)' {
        $init=Quest3-WaitLog $logFile 'LogInit: .*Engine is initialized|Game Engine Initialized' 180
        $map=Quest3-WaitLog $logFile 'LoadMap\(/Game/Quest/Maps/Verdant_Desktop|Bringing up level for play took|LogLoad: Took .* seconds to LoadMap' 240
        [ordered]@{ engine_initialized=$init; startup_map=$map; pid=(Quest3-Pid) }
    }
    Start-Sleep -Seconds 8
    Shot '01_title_menu' | Out-Null
    $report.menu_boot_lines=Step 'release front end booted (logcat)' { @((Select-String -LiteralPath $logFile -Pattern 'LogBlueprintUserMessages|ReleaseBoot|OpenXR|HMD|VrApi|LogHMD' | Select-Object -First 40 | ForEach-Object { $_.Line })) }
    Step 'New Game (Enter on the title row)' { Quest3-Key Enter } | Out-Null
    Start-Sleep -Seconds 4
    Shot '02_after_new_game' | Out-Null
    Step 'skip recollections (Space)' { Quest3-Key Space } | Out-Null
    Start-Sleep -Seconds 4
    Shot '03_surviving_room' | Out-Null
    Step 'pause (Escape)' { Quest3-Key Escape } | Out-Null
    Start-Sleep -Seconds 2
    Shot '04_pause' | Out-Null
    Step 'save committed progress (2)' { Quest3-Key Two } | Out-Null
    Start-Sleep -Seconds 3
    Shot '05_after_save' | Out-Null
    $report.save_directory=Step 'save directory after the first save' { Quest3-SaveDirectory }
    Step 'load saved progress (3)' { Quest3-Key Three } | Out-Null
    Start-Sleep -Seconds 4
    Shot '06_after_load' | Out-Null
    Step 'main menu (F10)' { Quest3-Key F10 } | Out-Null
    Start-Sleep -Seconds 3
    Shot '07_main_menu' | Out-Null
    Step 'Continue (Down, Enter)' { Quest3-Key Down | Out-Null; Start-Sleep -Milliseconds 600; Quest3-Key Enter } | Out-Null
    Start-Sleep -Seconds 4
    Shot '08_after_continue' | Out-Null
    Step 'main menu again (F10) and Quit (Down x4, Enter)' { Quest3-Key F10 | Out-Null; Start-Sleep -Seconds 2; foreach ($i in 1..4) { Quest3-Key Down | Out-Null; Start-Sleep -Milliseconds 500 }; Shot '09_quit_selected' | Out-Null; Quest3-Key Enter } | Out-Null
    $report.process_after_quit=Step 'process ended after Quit' { Start-Sleep -Seconds 6; $pidText=Quest3-Pid; [ordered]@{ pid=$pidText; ended=[string]::IsNullOrWhiteSpace($pidText) } }
    $report.pulled_saves=Step 'pull the guarded save files for inspection' {
        $dir=Quest3-SaveDirectory
        $names=@($dir.listing | ForEach-Object { ($_ -split '\s+')[-1] } | Where-Object { $_ -match '\.sav' })
        $pulled=@()
        foreach ($name in $names) {
            $local=Join-Path $evidence ('save_'+$name)
            try { $bytes=Quest3-PullSave $name $local; $head=[IO.File]::ReadAllBytes($local)[0..7]; $pulled += [ordered]@{ name=$name; bytes=$bytes; header=([Text.Encoding]::ASCII.GetString($head)); sha256=(Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash.ToLower() } }
            catch { $pulled += [ordered]@{ name=$name; error=$_.Exception.Message } }
        }
        [ordered]@{ directory=$dir; files=$pulled }
    }
    $report.crash_lines=@((Select-String -LiteralPath $logFile -Pattern 'FATAL|Fatal error|SIGSEGV|Assertion failed|LogAndroid: Error|libUnreal.*crash|ANR in' | Select-Object -First 20 | ForEach-Object { $_.Line }))
    $report.success=($report.process_after_quit.ended -and $report.crash_lines.Count -eq 0 -and @($report.screenshots | Where-Object { -not $_.ok }).Count -eq 0)
}
catch { $report.error=$_.Exception.Message }
finally {
    if ($logcat) { try { Stop-Process -Id $logcat.Id -Force } catch {} }
    try { $report.proximity_override_restored=Quest3-ProximityOverride $false } catch { $report.proximity_override_restored='failed: '+$_.Exception.Message }
    if (-not $KeepInstalled) { try { Quest3-Adb shell am force-stop $Quest3Package | Out-Null } catch {} }
    $report.steps=@($steps)
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidence 'smoke.json') -Encoding utf8
    Write-Output ('Quest 3 device smoke evidence: '+$evidence)
    [pscustomobject]$report | Select-Object run, success, error | ConvertTo-Json
}
