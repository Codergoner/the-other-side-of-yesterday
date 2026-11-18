[CmdletBinding()]
param(
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8',
    [string]$ArchiveDirectory = ''
)

# Installed-engine, Blueprint-only packaging. This uses the shipped UnrealGame
# executable and receipt; it does not compile C++, download SDKs, or install tools.
# Close project editor/QA sessions before running. Packaging itself has not been
# validated merely by checking this script's syntax and the installed UAT source.
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ArchiveDirectory)) {
    $ArchiveDirectory = Join-Path $PSScriptRoot '..\output\playable'
}
$taskProject = Join-Path $PSScriptRoot 'YesterdayHarbor.uproject'
$taskRunUat = Join-Path $EngineRoot 'Engine\Build\BatchFiles\RunUAT.bat'
$taskShipExe = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealGame-Win64-Shipping.exe'
$taskShipReceipt = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealGame-Win64-Shipping.target'
$taskAutomation = Join-Path $EngineRoot 'Engine\Binaries\DotNET\AutomationTool\AutomationTool.dll'
$taskArchive = [IO.Path]::GetFullPath($ArchiveDirectory)

foreach ($taskRequired in @($taskProject, $taskRunUat, $taskShipExe, $taskShipReceipt, $taskAutomation)) {
    if (-not (Test-Path -LiteralPath $taskRequired -PathType Leaf)) {
        throw "Installed-engine packaging file is missing: $taskRequired"
    }
}
$taskDescriptor = Get-Content -LiteralPath $taskProject -Raw | ConvertFrom-Json
if ($taskDescriptor.PSObject.Properties.Name -contains 'Modules') {
    throw 'This packaging script supports the existing Blueprint-only project. Native modules require a C++ toolchain.'
}
$taskEditors = Get-CimInstance Win32_Process -Filter "Name = 'UnrealEditor.exe' OR Name = 'UnrealEditor-Cmd.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -match '(?i)YesterdayHarbor\.uproject' }
if ($taskEditors) {
    throw 'Close the YesterdayHarbor editor and validation sessions before packaging the saved project.'
}

$taskUatArgs = @(
    'BuildCookRun'
    "-project=$taskProject"
    '-installed'
    '-nop4'
    '-unattended'
    '-utf8output'
    '-nocompile'
    '-nocompileuat'
    '-noautosdk'
    '-noturnkeyvariables'
    '-skipbuild'
    '-skipbuildeditor'
    '-skipbuildclient'
    '-platform=Win64'
    '-clientconfig=Shipping'
    '-cook'
    '-map=/Game/BriefTest/Maps/Quarter_ThirdPerson+/Game/BriefTest/Maps/Quarter_FirstPerson'
    '-stage'
    '-pak'
    '-iostore'
    '-compressed'
    '-package'
    '-archive'
    "-archivedirectory=$taskArchive"
    '-nodebuginfo'
)

& $taskRunUat @taskUatArgs
if ($LASTEXITCODE -ne 0) {
    throw "Unreal packaging failed with exit code $LASTEXITCODE. Read the AutomationTool log for the first error."
}
$taskWindows = Join-Path $taskArchive 'Windows'
$taskBootstrap = Join-Path $taskWindows 'YesterdayHarbor.exe'
if (-not (Test-Path -LiteralPath $taskBootstrap)) { throw 'UAT returned success without the expected game executable.' }
@'
@echo off
start "The Other Side of Yesterday" "%~dp0YesterdayHarbor.exe" -YesterdayFirstPerson -d3d11 -windowed -ResX=1600 -ResY=900
'@ | Set-Content -LiteralPath (Join-Path $taskWindows 'PlayFirstPerson.bat') -Encoding Ascii
@'
@echo off
start "The Other Side of Yesterday" "%~dp0YesterdayHarbor.exe" -YesterdayThirdPerson -d3d11 -windowed -ResX=1600 -ResY=900
'@ | Set-Content -LiteralPath (Join-Path $taskWindows 'PlayThirdPerson.bat') -Encoding Ascii
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'PACKAGED_PLAY_GUIDE.txt') -Destination (Join-Path $taskWindows 'PLAY_GUIDE.txt') -Force
[ordered]@{
    success = $true
    scope = 'Installed-engine Blueprint-only Windows Shipping cook, stage and archive'
    archive_directory = $taskWindows
    bootstrap = $taskBootstrap
    build_report_sha256 = [BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash([IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'chapters_story_build_report.json')))).Replace('-','')
    runtime_gameplay_tested = $false
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'packaged_build_report.json') -Encoding UTF8
Write-Host "Packaged Windows game archive: $taskArchive"
