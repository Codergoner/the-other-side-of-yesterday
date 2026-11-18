param([string]$OutputDirectory = (Join-Path $PSScriptRoot '../output/quest_android'))
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'UseQuestToolchain.ps1')
$questEngine = 'C:/Program Files/Epic Games/UE_5.8'
$questPython = Join-Path $questEngine 'Engine/Binaries/ThirdParty/Python3/Win64/python.exe'
$questPreflight = Join-Path $PSScriptRoot 'Python/quest_apk_preflight.py'
& $questPython $questPreflight --output (Join-Path $PSScriptRoot 'quest_apk_preflight.json')
if ($LASTEXITCODE -ne 0) {
    throw 'Quest prerequisites are incomplete. Inspect quest_apk_preflight.json. No packaging was attempted.'
}
$questUat = Join-Path $questEngine 'Engine/Build/BatchFiles/RunUAT.bat'
$questProject = Join-Path $PSScriptRoot 'YesterdayHarbor.uproject'
$questCookEditor = Join-Path $questEngine 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
$questArchive = [System.IO.Path]::GetFullPath($OutputDirectory)
& $questUat BuildCookRun "-project=$questProject" "-unrealexe=$questCookEditor" -noP4 -platform=Android -cookflavor=ASTC -clientconfig=Development -build -nocompileeditor -iterate -cook -stage -pak -package -archive "-archivedirectory=$questArchive" -map=/Game/Quest/Maps/Verdant_VR -utf8output
if ($LASTEXITCODE -ne 0) { throw "Quest packaging failed with exit $LASTEXITCODE. Inspect the Unreal AutomationTool log." }
Write-Output "Development Android output: $questArchive. Device deployment, stereo comfort and performance remain separate checks."
