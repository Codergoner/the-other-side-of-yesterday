param(
    [string]$Editor = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot.Replace('\', '/')
$taskProject = "$taskRoot/YesterdayHarbor.uproject"
$taskScript = "$taskRoot/Python/build_chapters_story.py"
if (-not (Test-Path -LiteralPath $Editor)) { throw "Unreal Editor not found: $Editor" }
if (-not (Test-Path -LiteralPath $taskProject)) { throw "Project not found: $taskProject" }
$taskActive = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in @('UnrealEditor.exe', 'UnrealEditor-Cmd.exe') -and
    $_.CommandLine -like '*YesterdayHarbor.uproject*'
}
if ($taskActive) { throw 'Close this project in Unreal before rebuilding its saved assets.' }
$taskReport = "$taskRoot/chapters_story_build_report.json"
if (Test-Path -LiteralPath $taskReport) { Remove-Item -LiteralPath $taskReport }
$taskBuild = Start-Process -FilePath $Editor -WindowStyle Hidden -PassThru -Wait -ArgumentList @(
    ('"' + $taskProject + '"'), '-unattended', '-nop4', '-nosplash', '-nosound', '-nullrhi',
    '-run=pythonscript', ('-script="' + $taskScript + '"')
) -RedirectStandardOutput "$taskRoot/chapters_build_stdout.log" -RedirectStandardError "$taskRoot/chapters_build_stderr.log"
if ($taskBuild.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $taskReport)) {
    throw "Build failed. Read $taskRoot/chapters_build_stdout.log"
}
$taskResult = Get-Content -LiteralPath $taskReport -Raw | ConvertFrom-Json
if (-not $taskResult.success) { throw $taskResult.error }
Write-Output 'Chapters 1–2 assets compiled and saved. Use a PlayHome launcher to play.'
