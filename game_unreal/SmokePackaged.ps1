[CmdletBinding()]
param(
    [string]$ArchiveDirectory = '',
    [ValidateSet('Quarter_ThirdPerson','Quarter_FirstPerson')][string]$Map = 'Quarter_ThirdPerson',
    [ValidateSet('Default','D3D11')][string]$RHI = 'Default',
    [switch]$UseBootstrap
)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ArchiveDirectory)) {
    $ArchiveDirectory = Join-Path $PSScriptRoot '..\output\playable\Windows'
}
$taskArchive = [IO.Path]::GetFullPath($ArchiveDirectory)
$taskBinary = Join-Path $taskArchive 'Engine\Binaries\Win64\UnrealGame-Win64-Shipping.exe'
if (-not (Test-Path -LiteralPath $taskBinary)) { throw "Packaged executable is missing: $taskBinary" }
$taskStamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$taskProfile = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\output\packaged_smoke\$taskStamp"))
New-Item -ItemType Directory -Path $taskProfile -Force | Out-Null
$taskConfig = Join-Path $taskProfile 'Saved\Config\Windows'
New-Item -ItemType Directory -Path $taskConfig -Force | Out-Null
@'
[/Script/Engine.GameUserSettings]
Version=5
FrameRateLimit=30.0
'@ | Set-Content -LiteralPath (Join-Path $taskConfig 'GameUserSettings.ini') -Encoding Ascii
$taskResult = [ordered]@{
    success = $false
    scope = 'Packaged Shipping startup and offscreen frame capture only'
    binary = $taskBinary
    map = "/Game/BriefTest/Maps/$Map"
    rhi = $RHI
    user_directory = $taskProfile
    keyboard_tested = $false
    packaged_story_routes_tested = $false
    termination = 'Supervisor-controlled after frame capture or deadline'
    test_frame_rate_limit = 30
    minimum_alive_seconds = 8
    bootstrap_tested = [bool]$UseBootstrap
}
$taskGame = $null
$taskBoot = $null
try {
    $taskLaunchArgs = @(
        '../../../YesterdayHarbor/YesterdayHarbor.uproject', ('-Yesterday' + $Map.Replace('Quarter_','')), '-RenderOffScreen', '-DUMPMOVIE',
        '-Windowed', '-ResX=960', '-ResY=540', '-ForceRes', '-Unattended', '-NoSound', '-NoSplash',
        ('-UserDir="' + $taskProfile.Replace('\','/') + '"')
    )
    if ($RHI -eq 'D3D11') { $taskLaunchArgs += '-d3d11' }
    if ($UseBootstrap) {
        $taskBootBinary = Join-Path $taskArchive 'YesterdayHarbor.exe'
        $taskBoot = Start-Process -FilePath $taskBootBinary -WorkingDirectory $taskArchive -WindowStyle Hidden -PassThru -ArgumentList $taskLaunchArgs[1..($taskLaunchArgs.Count-1)]
        $taskResult.bootstrap_pid = $taskBoot.Id
        $taskChildDeadline = (Get-Date).AddSeconds(10)
        do {
            Start-Sleep -Milliseconds 100
            $taskChild = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($taskBoot.Id)" | Where-Object { $_.ExecutablePath -eq $taskBinary } | Select-Object -First 1
        } while (-not $taskChild -and (Get-Date) -lt $taskChildDeadline)
        if (-not $taskChild) { throw 'Packaged bootstrap did not start its expected game child.' }
        $taskGame = Get-Process -Id $taskChild.ProcessId
    } else {
        $taskGame = Start-Process -FilePath $taskBinary -WorkingDirectory (Split-Path $taskBinary) -WindowStyle Hidden -PassThru -ArgumentList $taskLaunchArgs
    }
    $taskResult.pid = $taskGame.Id
    $taskDeadline = (Get-Date).AddSeconds(45)
    $taskMinimumEnd = (Get-Date).AddSeconds(8)
    $taskFrames = @()
    do {
        Start-Sleep -Milliseconds 500
        $taskGame.Refresh()
        $taskFrames = @(Get-ChildItem -LiteralPath $taskProfile -Recurse -Filter 'MovieFrame*.png' -ErrorAction SilentlyContinue | Where-Object { $_.Length -gt 15000 })
    } while (-not $taskGame.HasExited -and ($taskFrames.Count -lt 20 -or (Get-Date) -lt $taskMinimumEnd) -and (Get-Date) -lt $taskDeadline)
    $taskResult.frame_count = $taskFrames.Count
    $taskResult.frames = @($taskFrames | Sort-Object Name | Select-Object -ExpandProperty FullName)
    $taskResult.exited_before_supervisor_stop = $taskGame.HasExited
    if ($taskGame.HasExited) { $taskResult.exit_code = $taskGame.ExitCode }
    $taskResult.success = $taskFrames.Count -ge 20 -and -not $taskGame.HasExited
} finally {
    if ($taskGame) {
        $taskOwned = Get-CimInstance Win32_Process -Filter "ProcessId = $($taskGame.Id)"
        if ($taskOwned -and $taskOwned.ExecutablePath -eq $taskBinary) { Stop-Process -Id $taskGame.Id -Force -ErrorAction SilentlyContinue; $taskGame.WaitForExit(5000) | Out-Null }
    }
    if ($taskBoot) {
        $taskOwnedBoot = Get-CimInstance Win32_Process -Filter "ProcessId = $($taskBoot.Id)"
        if ($taskOwnedBoot -and $taskOwnedBoot.ExecutablePath -eq $taskBootBinary) { Stop-Process -Id $taskBoot.Id -Force -ErrorAction SilentlyContinue }
    }
    $taskResult | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $PSScriptRoot "packaged_startup_${Map}_${RHI}_validation.json") -Encoding UTF8
}
if (-not $taskResult.success) { throw 'Packaged render smoke did not produce the required frames; inspect packaged_startup_validation.json.' }
Write-Output "Packaged startup produced $($taskResult.frame_count) offscreen frames in $taskProfile"
