param([string]$OutputDirectory = (Join-Path $PSScriptRoot '../output/windows_release'), [switch]$FullCook)
$ErrorActionPreference = 'Stop'
$releaseEngine = 'C:/Program Files/Epic Games/UE_5.8'
$releaseProject = (Join-Path $PSScriptRoot 'YesterdayHarbor.uproject').Replace('\','/')
$releaseEditor = Join-Path $releaseEngine 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
$releaseUat = Join-Path $releaseEngine 'Engine/Build/BatchFiles/RunUAT.bat'
$releaseArchive = [IO.Path]::GetFullPath($OutputDirectory)
foreach ($releaseNeeded in @($releaseProject, $releaseEditor, $releaseUat, (Join-Path $releaseEngine 'Engine/Binaries/Win64/UnrealGame-Win64-Shipping.target'))) {
    if (-not (Test-Path -LiteralPath $releaseNeeded -PathType Leaf)) { throw ('Missing installed-engine packaging prerequisite: ' + $releaseNeeded) }
}
$releaseRunning = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^UnrealEditor' -and $_.CommandLine -like '*Release_20261026*' }
if ($releaseRunning) { throw 'Close release editor/QA processes before packaging.' }
$releaseIteration = @()
if (-not $FullCook) { $releaseIteration = @('-iterate') }
& $releaseUat BuildCookRun "-project=$releaseProject" "-unrealexe=$releaseEditor" -installed -nop4 -unattended -utf8output -nocompile -nocompileuat -noautosdk -noturnkeyvariables -skipbuild -skipbuildeditor -skipbuildclient -platform=Win64 -clientconfig=Shipping @releaseIteration -cook -map=/Game/Quest/Maps/Verdant_Desktop -stage -pak -iostore -compressed -package -archive "-archivedirectory=$releaseArchive" -nodebuginfo -prereqs
if ($LASTEXITCODE -ne 0) { throw ('Windows release packaging exited ' + $LASTEXITCODE + '; inspect UAT output for the first failure.') }
$releaseExecutable = Join-Path $releaseArchive 'YesterdayHarbor.exe'
if (-not (Test-Path -LiteralPath $releaseExecutable)) { $releaseExecutable = Join-Path $releaseArchive 'Windows/YesterdayHarbor.exe' }
if (-not (Test-Path -LiteralPath $releaseExecutable)) { throw 'UAT returned without the expected standalone executable in the archive root or Windows subfolder.' }
Write-Output ('Windows release package: ' + $releaseArchive + '. Package playthrough/capture remains a separate check.')
