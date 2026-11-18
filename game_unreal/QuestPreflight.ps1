param([switch]$Devices)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '../tools/android_toolchain_manifest.json')) {
    . (Join-Path $PSScriptRoot 'UseQuestToolchain.ps1')
}
$questPython = 'C:/Program Files/Epic Games/UE_5.8/Engine/Binaries/ThirdParty/Python3/Win64/python.exe'
if (-not (Test-Path -LiteralPath $questPython)) { throw 'Bundled UE Python is missing. No SDK or engine build has been attempted.' }
$questArgs = @((Join-Path $PSScriptRoot 'Python/quest_apk_preflight.py'), '--output', (Join-Path $PSScriptRoot 'quest_apk_preflight.json'))
if ($Devices) { $questArgs += '--devices' }
& $questPython @questArgs
exit $LASTEXITCODE
