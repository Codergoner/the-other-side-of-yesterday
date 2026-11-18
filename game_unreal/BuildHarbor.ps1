param([string]$UnrealEditor = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe')
$taskProjectRoot = $PSScriptRoot.Replace('\', '/')
& $UnrealEditor "$taskProjectRoot/YesterdayHarbor.uproject" -unattended -nop4 -nosplash -nosound -nullrhi -run=pythonscript "-script=$taskProjectRoot/Python/import_harbor.py"
if ($LASTEXITCODE -ne 0) { throw "Harbor import failed; inspect import_report.json and Saved/Logs." }
