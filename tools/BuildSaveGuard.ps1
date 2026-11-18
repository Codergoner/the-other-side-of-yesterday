$ErrorActionPreference = 'Stop'
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
# Version 5 compiles the guard for Win64 and Android (Meta Quest 3). The portable Android
# toolchain is applied to this process only (no registry or user PATH change).
. (Join-Path $releaseRoot 'game_unreal/UseQuestToolchain.ps1')
$releaseTargetPlatforms = 'Win64+Android'
$releaseBuildStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss_fffffff')
$releaseEvidenceRoot = Join-Path $releaseRoot ('output/save_guard_builds/' + $releaseBuildStamp)
# UBT rejects generated action paths >=260 chars. Use a short isolated build
# directory; preserve original projects and Windows path-policy settings.
$releaseBuildRoot = Join-Path $env:LOCALAPPDATA ('TOSOYBuild/SG/' + $releaseBuildStamp)
New-Item -ItemType Directory -Path $releaseBuildRoot -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Path $releaseEvidenceRoot -ErrorAction Stop | Out-Null
$releaseSnapshot = Join-Path $releaseBuildRoot 'source/YesterdaySaveGuard'
New-Item -ItemType Directory -Path (Split-Path $releaseSnapshot) -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $releaseRoot 'native_save_guard/YesterdaySaveGuard') -Destination $releaseSnapshot -Recurse
$releaseHashes = @(Get-ChildItem -LiteralPath $releaseSnapshot -File -Recurse | ForEach-Object {
    [ordered]@{path=$_.FullName.Substring($releaseSnapshot.Length+1);sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}
})
[ordered]@{snapshot=$releaseSnapshot;created_utc=[DateTime]::UtcNow.ToString('o');files=$releaseHashes;source_only_before_build=$true} |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $releaseEvidenceRoot 'source_manifest.json')
$releasePlugin = Join-Path $releaseSnapshot 'YesterdaySaveGuard.uplugin'
$releasePackage = Join-Path $releaseBuildRoot 'package'
& 'C:/Program Files/Epic Games/UE_5.8/Engine/Build/BatchFiles/RunUAT.bat' BuildPlugin "-Plugin=$releasePlugin" "-Package=$releasePackage" "-TargetPlatforms=$releaseTargetPlatforms" -Rocket 2>&1 |
    Tee-Object -FilePath (Join-Path $releaseEvidenceRoot 'build.log')
$releaseBuildExit = $LASTEXITCODE
[ordered]@{exit_code=$releaseBuildExit;completed_utc=[DateTime]::UtcNow.ToString('o');package=$releasePackage;target_platforms=$releaseTargetPlatforms;android_ndk=$env:NDKROOT;scope='Actual isolated plugin compile/link for Win64 and Android; not integrated or fault-tested'} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $releaseEvidenceRoot 'build_result.json')
Write-Output ('SaveGuard build evidence: ' + $releaseEvidenceRoot)
exit $releaseBuildExit
