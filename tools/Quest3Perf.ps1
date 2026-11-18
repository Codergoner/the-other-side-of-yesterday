param(
    [Parameter(Mandatory=$true)][string]$Apk,
    [ValidateSet('Shipping','Development')][string]$Configuration='Development',
    [int]$SampleSeconds=20,
    [switch]$RouteSweep,
    [string]$BuildEvidence=''
)
# Frame-time evidence on the connected Quest 3: the runtime's periodic frame lines in logcat (FPS, app GPU
# time, CPU/GPU levels, temperature) during the title menu and the surviving room after New Game, plus, on a
# Development package, a console-driven sweep of the route (pawn placed at the authored landing positions in
# both eras, repeated era transitions, engine CSV profile). Headset on the desk with the proximity override:
# tracking is static, so this is a static-view measurement, labelled as such. Output: output/quest3_perf/<stamp>/.
$ErrorActionPreference='Stop'
$releaseRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if ((Split-Path -Leaf $releaseRoot) -ne 'Release_20261026') { throw 'Perf capture runs only from the Release copy.' }
. (Join-Path $PSScriptRoot 'Quest3Device.ps1')
$apkFile=Get-Item -LiteralPath $Apk
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmss')
$evidence=Join-Path $releaseRoot ('output/quest3_perf/'+$stamp)
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$shots=Join-Path $evidence 'screenshots'
$logFile=Join-Path $evidence 'logcat.txt'
# Landing positions (cm) from the 4 November inventory; pawn root = floor + 88 (capsule half height).
$waypoints=@(
    @{ id='home_inside'; x=-620; y=1240; z=1099 }, @{ id='home_porch'; x=-300; y=1240; z=1099 }, @{ id='gate'; x=50; y=1240; z=984 },
    @{ id='clinic_street'; x=50; y=740; z=1034 }, @{ id='clinic_approach'; x=-40; y=580; z=1050 }, @{ id='market_street'; x=30; y=0; z=1108 },
    @{ id='sela_service'; x=30; y=-300; z=1138 }, @{ id='market_arcade'; x=-600; y=-200; z=1138 }, @{ id='harbor_choice'; x=-45; y=-535; z=1161.5 },
    @{ id='sea_pause'; x=50; y=-900; z=1198 }, @{ id='upper_street'; x=50; y=-1400; z=1248 }, @{ id='upper_overlook'; x=450; y=-1400; z=1248 })
$report=[ordered]@{ run=$stamp; utc=[DateTime]::UtcNow.ToString('o'); apk=$apkFile.FullName; apk_sha256=(Get-FileHash -LiteralPath $apkFile.FullName -Algorithm SHA256).Hash.ToLower(); configuration=$Configuration;
    build_evidence=$BuildEvidence; package=$Quest3Package; sample_seconds=$SampleSeconds; samples=@(); success=$false;
    method='Runtime frame lines (FPS=, App=, GPU%, CPU%, Temp) parsed from adb logcat per labelled window; static headset view with the proximity override; Development builds also run the engine csvprofile and console-driven placement';
    scope='Static-view device frame-time measurement; not a worn playthrough; comfort and tracking judgements belong to the wearer script' }
function Save { $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidence 'perf.json') -Encoding utf8 }
function Frame-Lines([datetime]$from,[datetime]$to) {
    $rows=@()
    if (-not (Test-Path -LiteralPath $logFile)) { return $rows }
    foreach ($line in Get-Content -LiteralPath $logFile) {
        if ($line -notmatch 'FPS=(\d+)/(\d+)') { continue }
        if ($line -match '^(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)\.(\d\d\d)') {
            $t=Get-Date -Month ([int]$Matches[1]) -Day ([int]$Matches[2]) -Hour ([int]$Matches[3]) -Minute ([int]$Matches[4]) -Second ([int]$Matches[5]) -Millisecond ([int]$Matches[6])
            if ($t -lt $from -or $t -gt $to) { continue }
        }
        $row=[ordered]@{ fps=[int]$Matches[1]; target=[int]$Matches[2] }
        if ($line -match 'App=([\d\.]+)ms') { $row.app_ms=[double]$Matches[1] }
        if ($line -match 'TW=([\d\.]+)ms') { $row.timewarp_ms=[double]$Matches[1] }
        if ($line -match 'CPU&GPU=([\d\.]+)ms') { $row.cpu_gpu_ms=[double]$Matches[1] }
        if ($line -match 'GPU%=([\d\.]+)') { $row.gpu_util=[double]$Matches[1] }
        if ($line -match 'CPU%=([\d\.]+)') { $row.cpu_util=[double]$Matches[1] }
        if ($line -match 'Stale=(\d+)') { $row.stale=[int]$Matches[1] }
        if ($line -match 'Temp=([\d\.]+)C') { $row.temp_c=[double]$Matches[1] }
        if ($line -match 'CPU\d/GPU=(\d)/(\d)') { $row.cpu_level=[int]$Matches[1]; $row.gpu_level=[int]$Matches[2] }
        if ($line -match 'Free=(\d+)MB') { $row.free_mb=[int]$Matches[1] }
        $rows += $row
    }
    return $rows
}
function Summarise($rows) {
    if (-not $rows -or $rows.Count -eq 0) { return [ordered]@{ lines=0; note='no runtime frame lines in this window (tag not emitted or app not foreground)' } }
    $fps=@($rows | ForEach-Object { $_.fps }) | Sort-Object
    $app=@($rows | Where-Object { $_.app_ms } | ForEach-Object { $_.app_ms }) | Sort-Object
    $pct={ param($arr,$p) if ($arr.Count -eq 0) { $null } else { $arr[[math]::Min($arr.Count-1,[math]::Floor($arr.Count*$p))] } }
    [ordered]@{ lines=$rows.Count; target_hz=($rows[0].target); fps_min=$fps[0]; fps_median=(& $pct $fps .5); fps_p05=(& $pct $fps .05); fps_mean=[math]::Round(($fps | Measure-Object -Average).Average,1);
        app_ms_median=(& $pct $app .5); app_ms_p95=(& $pct $app .95); app_ms_max=$(if ($app.Count) { $app[-1] } else { $null });
        stale_total=(($rows | Where-Object { $_.stale } | ForEach-Object { $_.stale } | Measure-Object -Sum).Sum);
        gpu_util_max=(($rows | Where-Object { $_.gpu_util } | ForEach-Object { $_.gpu_util } | Measure-Object -Maximum).Maximum);
        temp_c_max=(($rows | Where-Object { $_.temp_c } | ForEach-Object { $_.temp_c } | Measure-Object -Maximum).Maximum);
        free_mb_min=(($rows | Where-Object { $_.free_mb } | ForEach-Object { $_.free_mb } | Measure-Object -Minimum).Minimum) }
}
function Sample([string]$label,[hashtable]$extra) {
    $from=Get-Date
    Start-Sleep -Seconds $SampleSeconds
    $to=Get-Date
    $rows=Frame-Lines $from $to
    $shot=Quest3-Screenshot $shots $label
    $row=[ordered]@{ label=$label; from=$from.ToString('o'); to=$to.ToString('o'); summary=(Summarise $rows); frames=$rows; screenshot=$shot }
    if ($extra) { foreach ($k in $extra.Keys) { $row[$k]=$extra[$k] } }
    $report.samples=@($report.samples)+@($row)
    Save
    return $row
}
$logcat=$null
try {
    $device=Quest3-RequireDevice
    $report.device=$device
    $report.device_properties=Quest3-Props
    Quest3-Adb shell am force-stop $Quest3Package | Out-Null
    if (Quest3-Installed) { Quest3-Adb uninstall $Quest3Package | Out-Null }
    $install=Quest3-Adb install -r -g $apkFile.FullName
    if ($install.text -notmatch 'Success') { throw ('adb install: '+$install.text) }
    $report.installed_version=Quest3-PackageVersion
    Quest3-ProximityOverride $true | Out-Null
    $logcat=Quest3-StartLogcat $logFile
    $launchStart=Get-Date
    $report.launch=Quest3-Launch
    $report.cold_start=[ordered]@{ engine=(Quest3-WaitLog $logFile 'LogInit: .*Engine is initialized|Game Engine Initialized' 180); map=(Quest3-WaitLog $logFile 'LoadMap\(/Game/Quest/Maps/Verdant_Desktop|LogLoad: Took .* seconds to LoadMap|Bringing up level for play took' 240) }
    $report.cold_start.wall_seconds_to_map=[math]::Round(((Get-Date)-$launchStart).TotalSeconds,1)
    Save
    Start-Sleep -Seconds 6
    Sample 'title_menu' @{ state='release title menu on the world panel' } | Out-Null
    Quest3-Key Enter | Out-Null; Start-Sleep -Seconds 4; Quest3-Key Space | Out-Null; Start-Sleep -Seconds 4
    Sample 'surviving_room_present' @{ state='New Game, recollections skipped, present era, home' } | Out-Null
    if ($RouteSweep -and $Configuration -eq 'Development') {
        $report.console_probe=Quest3-Console 'stat none'
        $names=(Quest3-Adb shell am broadcast -a android.intent.action.RUN -e cmd '"getall BP_QuestCharacter_C Name"').text
        Start-Sleep -Seconds 1
        $pawn=(Select-String -LiteralPath $logFile -Pattern 'BP_QuestCharacter_C_\d+' -AllMatches | ForEach-Object { $_.Matches } | ForEach-Object { $_.Value } | Select-Object -Last 1)
        $report.pawn_name=$pawn
        if (-not $pawn) { $pawn='BP_QuestCharacter_C_0'; $report.pawn_name_assumed=$true }
        Quest3-Console 'csvprofile start' | Out-Null
        foreach ($era in @(0,1)) {
            Quest3-Console ('set BP_OpeningActions_C EraIndex '+$era) | Out-Null
            Quest3-Console 'ke * ApplyWorldState' | Out-Null
            Start-Sleep -Seconds 3
            foreach ($w in $waypoints) {
                Quest3-Console ('ke '+$pawn+' K2_SetActorLocation (X='+$w.x+',Y='+$w.y+',Z='+$w.z+') false false') | Out-Null
                Start-Sleep -Seconds 3
                Sample (('era{0}_{1}' -f $era,$w.id)) @{ era=$era; waypoint=$w; placement='console K2_SetActorLocation (profiling only)' } | Out-Null
            }
        }
        $transitions=@()
        for ($i=0; $i -lt 6; $i++) {
            $era=$i % 2
            $t0=Get-Date
            Quest3-Console ('set BP_OpeningActions_C EraIndex '+$era) | Out-Null
            Quest3-Console 'ke * ApplyWorldState' | Out-Null
            Start-Sleep -Seconds 4
            $transitions += [ordered]@{ index=$i; era=$era; frames=(Frame-Lines $t0 (Get-Date)) }
        }
        $report.era_transitions=$transitions
        $report.era_transition_summary=Summarise (@($transitions | ForEach-Object { $_.frames } | ForEach-Object { $_ }))
        Quest3-Console 'csvprofile stop' | Out-Null
        Start-Sleep -Seconds 3
        $csvList=Quest3-Adb shell run-as $Quest3Package ls -R files/UnrealGame/YesterdayHarbor/YesterdayHarbor/Saved/Profiling
        $report.csv_profiles=$csvList.lines
        foreach ($line in $csvList.lines) { if ($line -match '\.csv$') { try { $local=Join-Path $evidence $line.Trim(); $bytes=& $Quest3Adb exec-out run-as $Quest3Package cat ('files/UnrealGame/YesterdayHarbor/YesterdayHarbor/Saved/Profiling/CSV/'+$line.Trim()); [IO.File]::WriteAllBytes($local,[byte[]]$bytes) } catch { $report.csv_pull_error=$_.Exception.Message } } }
    }
    $report.success=(@($report.samples | Where-Object { $_.summary.lines -gt 0 }).Count -gt 0)
}
catch { $report.error=$_.Exception.Message }
finally {
    if ($logcat) { try { Stop-Process -Id $logcat.Id -Force } catch {} }
    try { Quest3-Adb shell am force-stop $Quest3Package | Out-Null } catch {}
    try { $report.proximity_override_restored=Quest3-ProximityOverride $false } catch {}
    Save
    Write-Output ('Quest 3 perf evidence: '+$evidence)
    [pscustomobject]$report | Select-Object run, success, error | ConvertTo-Json
}
