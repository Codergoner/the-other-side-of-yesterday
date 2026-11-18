$ErrorActionPreference = 'Stop'
$releaseProject = (Join-Path $PSScriptRoot 'YesterdayHarbor.uproject').Replace('\','/')
$releaseScript = (Join-Path $PSScriptRoot 'Python/capture_release_baseline.py').Replace('\','/')
$releaseLog = (Join-Path $PSScriptRoot 'release_m0_capture_native.log').Replace('\','/')
$releaseArgs = '"' + $releaseProject + '" -d3d11 -unattended -nosplash -NoSound -ExecutePythonScript="' + $releaseScript + '" -QuestArtHouseHero -abslog="' + $releaseLog + '"'
$releaseProcess = Start-Process -FilePath 'C:/Program Files/Epic Games/UE_5.8/Engine/Binaries/Win64/UnrealEditor.exe' -ArgumentList $releaseArgs -WindowStyle Hidden -PassThru
Write-Output ('Release baseline capture PID ' + $releaseProcess.Id)
