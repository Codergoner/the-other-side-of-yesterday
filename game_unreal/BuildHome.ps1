param([string]$UnrealEditor = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe')
$taskHomeProjectRoot = $PSScriptRoot.Replace('\', '/')
& $UnrealEditor "$taskHomeProjectRoot/YesterdayHarbor.uproject" -unattended -nop4 -nosplash -nosound -nullrhi -run=pythonscript "-script=$taskHomeProjectRoot/Python/import_house.py"
if ($LASTEXITCODE -ne 0) { throw "Home import failed; inspect house_import_report.json and Saved/Logs." }
