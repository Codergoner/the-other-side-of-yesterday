param(
    [ValidateSet('Play','Smoke','Check')][string]$Mode = 'Play',
    [string]$RuntimeJson = '',
    [string]$Map = '/Game/Quest/Maps/Verdant_Desktop',
    [int]$SmokeSeconds = 90,
    [int]$ResX = 1280,
    [int]$ResY = 720,
    [string]$UserDir = '',
    [switch]$NoSimulatorWindow
)
# Runs the Quest 3 game (the same map, game mode and pawn as the APK) through Meta XR Simulator on this PC.
#
#   Check : only look for the simulator and report what would be launched (starts nothing).
#   Play  : launch the game in VR through the simulator and leave it running for a person (see docs/PLAY_IN_SIMULATOR.md).
#   Smoke : launch, wait -SmokeSeconds, read the game log, write a pass/fail report, quit the game.
#
# Evidence label for everything this produces: simulator-tested (OpenXR API on Windows). The simulator models the OpenXR
# API only. It does not run the Android APK and says nothing about Quest GPU speed, thermal behaviour or comfort.
#
# The simulator is selected for the launched game process ONLY, through the XR_RUNTIME_JSON environment variable of this
# script's own process. The system-wide active OpenXR runtime (HKLM\SOFTWARE\Khronos\OpenXR\1) is never read for change,
# written or toggled, and the simulator's activate_simulator.ps1 / "set as active runtime" switch is never used.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if ((Split-Path -Leaf $root) -ne 'Release_20261026') { throw 'The simulator run is for the Release copy only' }

function Find-Runtime {
    if ($RuntimeJson) { return (Resolve-Path -LiteralPath $RuntimeJson).Path }
    $base = Join-Path $env:ProgramFiles 'MetaXRSimulator'
    if (-not (Test-Path -LiteralPath $base)) { return $null }
    $candidates = Get-ChildItem -LiteralPath $base -Directory -Filter 'v*' -ErrorAction SilentlyContinue |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'meta_openxr_simulator.json') } |
        Sort-Object { try { [version]($_.Name.TrimStart('v')) } catch { [version]'0.0' } } -Descending
    if ($candidates) { return (Join-Path $candidates[0].FullName 'meta_openxr_simulator.json') }
    return $null
}

$runtime = Find-Runtime
if (-not $runtime) {
    Write-Output @'
Meta XR Simulator was not found, so nothing was started.

Install it once (Windows, free): https://developers.meta.com/vr/downloads/package/meta-xr-simulator-windows/
The default install folder is C:\Program Files\MetaXRSimulator\v<version>. This script looks for
meta_openxr_simulator.json there. If you installed it elsewhere, run:

    powershell -File tools/RunQuest3Simulator.ps1 -Mode Play -RuntimeJson "D:\path\to\meta_openxr_simulator.json"

Do not switch the simulator on as the system-wide OpenXR runtime; this script selects it for the game process only.
'@
    exit 2
}
$runtimeDir = Split-Path -Parent $runtime
$manifest = Get-Content -LiteralPath $runtime -Raw | ConvertFrom-Json
$library = [IO.Path]::GetFullPath((Join-Path $runtimeDir $manifest.runtime.library_path))
if (-not (Test-Path -LiteralPath $library)) { throw "The runtime library named by $runtime is missing: $library" }
$simulatorApp = Join-Path $runtimeDir 'MetaXRSimulator.exe'
$editor = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$project = (Join-Path $root 'game_unreal\YesterdayHarbor.uproject')
$activeKey = 'HKLM:\SOFTWARE\Khronos\OpenXR\1'
$activeBefore = $null
try { $activeBefore = (Get-ItemProperty -LiteralPath $activeKey -Name ActiveRuntime -ErrorAction Stop).ActiveRuntime } catch { $activeBefore = $null }

$stamp = Get-Date -Format 'yyyyMMddTHHmmss'
$evidence = Join-Path $root ('output\quest3_simulator\' + $stamp)
$plan = [ordered]@{
    stamp = $stamp; mode = $Mode; evidence_label = 'simulator-tested (OpenXR API on Windows); not device-tested'
    runtime_manifest = $runtime; runtime_name = $manifest.runtime.name; runtime_library = $library
    simulator_app = $(if (Test-Path -LiteralPath $simulatorApp) { $simulatorApp } else { $null })
    system_active_runtime_before = $activeBefore
    launch = 'UnrealEditor.exe -game -vr -d3d11 (uncooked Release project, same map, game mode and pawn as the APK)'
    map = $Map
}
if ($Mode -eq 'Check') { $plan | ConvertTo-Json; exit 0 }

if (-not (Test-Path -LiteralPath $editor)) { throw "Unreal Engine 5.8 not found at $editor" }
$busy = @(Get-Process -Name 'UnrealEditor','UnrealEditor-Cmd' -ErrorAction SilentlyContinue)
if ($busy.Count -gt 0) { throw ('Another Unreal process is running (one at a time): ' + (($busy | ForEach-Object { $_.ProcessName + ':' + $_.Id }) -join ', ')) }
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$log = Join-Path $evidence 'game.log'
# Play keeps one stable folder so your saves persist between sessions; Smoke uses a fresh folder every time.
$user = if ($UserDir) { $UserDir } elseif ($Mode -eq 'Play') { Join-Path $env:LOCALAPPDATA 'TOSOYQA\Simulator_Play' } else { Join-Path $env:LOCALAPPDATA ('TOSOYQA\Simulator_' + $stamp) }
New-Item -ItemType Directory -Force -Path $user | Out-Null

# The simulator window shows the headset view, frame rate and the input panels. Start it first when it is not open.
$startedSimulator = $false
if (-not $NoSimulatorWindow -and (Test-Path -LiteralPath $simulatorApp) -and -not (Get-Process -Name 'MetaXRSimulator' -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $simulatorApp -WorkingDirectory $runtimeDir | Out-Null
    $startedSimulator = $true
    Start-Sleep -Seconds 4
}

$url = $Map + '?game=/Game/Quest/XR/BP_QuestGameMode.BP_QuestGameMode_C'
# The project allow-lists OpenXR and the hand-tracking plugins to Android only (the APK path). For this Windows run they are
# enabled on the command line instead of editing the project file, so the Windows project settings stay as they were.
$arguments = @(('"' + $project + '"'), $url, '-game', '-vr', '-hmd=OpenXR', '-EnablePlugins=OpenXR,OpenXRHandTracking,OpenXRMsftHandInteraction',
               '-d3d11', '-windowed', "-ResX=$ResX", "-ResY=$ResY", '-nosplash',
               ('-abslog="' + $log + '"'), ('-UserDir="' + $user.Replace('\','/') + '/"'), '-LogCmds="LogHMD Log, LogOpenXR Log, LogXR Log"')
$previous = $env:XR_RUNTIME_JSON
$env:XR_RUNTIME_JSON = $runtime
try {
    $process = Start-Process -FilePath $editor -ArgumentList $arguments -WorkingDirectory $root -PassThru
} finally {
    if ($null -eq $previous) { Remove-Item Env:\XR_RUNTIME_JSON -ErrorAction SilentlyContinue } else { $env:XR_RUNTIME_JSON = $previous }
}
$plan.game_pid = $process.Id
$plan.game_log = $log
$plan.user_dir = $user
$plan.started_simulator_window = $startedSimulator
Write-Output ("Game started (pid {0}) through {1}. Log: {2}" -f $process.Id, $manifest.runtime.name, $log)

if ($Mode -eq 'Play') {
    Write-Output 'Play mode: the game keeps running. Follow docs/PLAY_IN_SIMULATOR.md. Close the game window when you are done.'
    $plan | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'launch.json') -Encoding utf8
    exit 0
}

# Smoke: let the session settle, read the log, then quit.
Start-Sleep -Seconds $SmokeSeconds
$alive = -not $process.HasExited
$lines = @()
if (Test-Path -LiteralPath $log) { $lines = @(Get-Content -LiteralPath $log -ErrorAction SilentlyContinue | ForEach-Object { [string]$_ }) }
if ($alive) {
    [void]$process.CloseMainWindow()
    if (-not $process.WaitForExit(15000)) { Stop-Process -Id $process.Id -Force }
}
if ($startedSimulator) { Get-Process -Name 'MetaXRSimulator' -ErrorAction SilentlyContinue | Stop-Process -Force }
$telemetry = @($lines | Where-Object { $_ -match 'QUESTXR hmd=' })
$parsed = @($telemetry | ForEach-Object {
    $o = [ordered]@{}
    if ($_ -match 'hmd=(\w+) rightHand=(\w+) leftHand=(\w+) rightPinch=(\w+) leftPinch=(\w+) gaze=(\w+) coach=(\d+) mode=(\d+) fps=(\d+) debounced=(\d+) hint=(.*?) actions=(.*)$') {
        $o.hmd = $Matches[1]; $o.right_hand = $Matches[2]; $o.left_hand = $Matches[3]; $o.mode = [int]$Matches[8]; $o.fps = [int]$Matches[9]; $o.hint = $Matches[11]; $o.actions = $Matches[12]
    }
    [pscustomobject]$o
})
$runtimeLines = @($lines | ForEach-Object { [string]$_ } | Where-Object { $_ -match 'OpenXR|XR_RUNTIME|SIMULATOR|Meta OpenXR Simulator|LogHMD' } | ForEach-Object { if ($_.Length -gt 300) { $_.Substring(0, 300) } else { $_ } } | Select-Object -First 40)
$fps = @($parsed | Where-Object { $_.fps -gt 0 } | ForEach-Object { $_.fps })
$report = [ordered]@{
    stamp = $stamp; evidence_label = $plan.evidence_label
    runtime = $manifest.runtime.name; runtime_manifest = $runtime
    survived_smoke_seconds = $alive
    log_lines = $lines.Count
    telemetry_lines = $telemetry.Count
    hmd_active_seen = [bool]($parsed | Where-Object { $_.hmd -eq 'true' })
    hand_tracking_seen = [bool]($parsed | Where-Object { $_.right_hand -eq 'true' -or $_.left_hand -eq 'true' })
    hand_actions_seen = @($parsed | Where-Object { $_.actions } | ForEach-Object { $_.actions }) -join ' '
    fps_samples = $fps.Count
    fps_min = $(if ($fps) { ($fps | Measure-Object -Minimum).Minimum } else { $null })
    fps_max = $(if ($fps) { ($fps | Measure-Object -Maximum).Maximum } else { $null })
    fps_note = 'Frame rate of the editor-hosted game on this PC through the simulator. Not Quest performance.'
    system_active_runtime_before = $activeBefore
    runtime_log_excerpt = $runtimeLines
}
$activeAfter = $null
try { $activeAfter = (Get-ItemProperty -LiteralPath $activeKey -Name ActiveRuntime -ErrorAction Stop).ActiveRuntime } catch { $activeAfter = $null }
$report.system_active_runtime_after = $activeAfter
$report.system_runtime_unchanged = ($activeBefore -eq $activeAfter)
$report.pass = ($alive -and $report.hmd_active_seen -and $report.system_runtime_unchanged)
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'smoke_report.json') -Encoding utf8
$report | ConvertTo-Json -Depth 5
if (-not $report.pass) { exit 1 }


