param(
    [string]$Filter = 'Yesterday.SaveGuard',
    [int]$TimeoutSeconds = 900
)
# Runs the native SaveGuard automation tests (BoundedDecoder, StoryV2Migration, IdentityV2Migration)
# in the Release copy's editor (nullrhi, isolated short UserDir) and records the per-test results.
# Windows PowerShell 5.1. Refuses while another Unreal/Blender process runs (one native process at a time).
$ErrorActionPreference = 'Stop'
$releaseRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if ((Split-Path -Leaf $releaseRoot) -ne 'Release_20261026') { throw 'Automation runs only in the Release copy.' }
if (Get-Process UnrealEditor,UnrealEditor-Cmd,blender -ErrorAction SilentlyContinue) { throw 'Another Unreal/Blender process is running.' }
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss_fffffff')
$evidence = Join-Path $releaseRoot ('output/save_guard_automation/' + $stamp)
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$userDir = Join-Path 'C:\Users\USER\TOSOYReleaseQA' ('GuardAutomation_' + $stamp.Substring(0, 15))
New-Item -ItemType Directory -Path $userDir -Force | Out-Null
$project = (Join-Path $releaseRoot 'game_unreal\YesterdayHarbor.uproject').Replace('\', '/')
$log = (Join-Path $evidence 'automation.log').Replace('\', '/')
$report = (Join-Path $evidence 'report').Replace('\', '/')
$plugin = Get-Content -LiteralPath (Join-Path $releaseRoot 'game_unreal\Plugins\YesterdaySaveGuard\YesterdaySaveGuard.uplugin') -Raw | ConvertFrom-Json
$arguments = @(('"' + $project + '"'), '-unattended', '-nopause', '-nosplash', '-NoSound', '-nullrhi', '-nop4',
    ('-UserDir="' + $userDir.Replace('\', '/') + '/"'), ('-abslog="' + $log + '"'), ('-ReportExportPath="' + $report + '"'),
    ('-ExecCmds="Automation RunTests ' + $Filter + ';Quit"'), '-TestExit="Automation Test Queue Empty"')
$editor = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$started = [DateTime]::UtcNow
$process = Start-Process -FilePath $editor -ArgumentList $arguments -WorkingDirectory $releaseRoot -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit($TimeoutSeconds * 1000)) { Stop-Process -Id $process.Id -Force; throw "Automation timed out after $TimeoutSeconds s; log $log" }
# UE 5.8 logs "Test Completed. Result={Success|Fail} ..."; the exported index.json is kept beside the log.
$results = @()
if (Test-Path -LiteralPath $log) {
    foreach ($line in Get-Content -LiteralPath $log) {
        if ($line -match 'LogAutomationController: Display: Test Completed\. Result=\{(\w+)\} Name=\{([^}]+)\} Path=\{([^}]+)\}') {
            $results += [ordered]@{ result = $Matches[1]; name = $Matches[2]; path = $Matches[3]; passed = ($Matches[1] -in @('Success', 'Passed')) }
        }
    }
}
$exported = $null
$index = Join-Path $report 'index.json'
if (Test-Path -LiteralPath $index) { $exported = Get-Content -LiteralPath $index -Raw | ConvertFrom-Json }
$summary = [ordered]@{
    run = $stamp; utc = $started.ToString('o'); filter = $Filter; exit_code = $process.ExitCode; seconds = [int]([DateTime]::UtcNow - $started).TotalSeconds
    plugin_version = $plugin.Version; plugin_version_name = $plugin.VersionName; user_dir = $userDir; log = $log; report_export = $report
    tests = $results; passed = @($results | Where-Object { $_.passed }).Count; failed = @($results | Where-Object { -not $_.passed }).Count
    exported_report = if ($exported) { [ordered]@{ succeeded = $exported.succeeded; failed = $exported.failed; not_run = $exported.notRun; total_duration = $exported.totalDuration } } else { $null }
    success = ($results.Count -gt 0 -and @($results | Where-Object { -not $_.passed }).Count -eq 0)
    scope = 'Editor-context native automation (nullrhi); not a PIE, packaged, disk-fault or power-loss test.'
}
$summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'summary.json') -Encoding utf8
[pscustomobject]$summary | Select-Object run, exit_code, seconds, plugin_version, passed, failed, success | ConvertTo-Json
$results | ForEach-Object { '{0}: {1}' -f $_.result, $_.path }
