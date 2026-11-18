param([Parameter(Mandatory=$true)][string]$Evidence)
$ErrorActionPreference='Stop'
$releaseRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$evidenceRoot=[IO.Path]::GetFullPath($Evidence)
$built=Get-Content -LiteralPath (Join-Path $evidenceRoot 'build_result.json') -Raw | ConvertFrom-Json
if ($built.exit_code -ne 0) { throw 'The actual BuildPlugin run did not succeed.' }
$package=[IO.Path]::GetFullPath($built.package)
$snapshot=Get-Content -LiteralPath (Join-Path $evidenceRoot 'source_manifest.json') -Raw | ConvertFrom-Json
$sourceRoot=Join-Path $releaseRoot 'native_save_guard/YesterdaySaveGuard'
$sourceFiles=@()
foreach ($entry in $snapshot.files) {
    $source=Join-Path $sourceRoot $entry.path
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $entry.sha256) { throw ('Current candidate source changed from actual compiled snapshot: '+$entry.path) }
    if ($entry.path.StartsWith('Source')) {
        if ((Get-FileHash -LiteralPath (Join-Path $package $entry.path) -Algorithm SHA256).Hash -ne $entry.sha256) { throw 'Packaged source differs from compiled source snapshot.' }
    }
    $sourceFiles += [ordered]@{source=$entry.path;sha256=$entry.sha256;current_source_matches=$true}
}
$modules=Get-Content -LiteralPath (Join-Path $package 'Binaries/Win64/UnrealEditor.modules') -Raw | ConvertFrom-Json
$engine=Get-Content -LiteralPath 'C:/Program Files/Epic Games/UE_5.8/Engine/Binaries/Win64/UnrealEditor.modules' -Raw | ConvertFrom-Json
if ($modules.BuildId -ne $engine.BuildId -or $modules.Modules.YesterdaySaveGuard -ne 'UnrealEditor-YesterdaySaveGuard.dll') { throw 'Native Editor module ABI/build identity mismatch.' }
$descriptor=Get-Content -LiteralPath (Join-Path $package 'YesterdaySaveGuard.uplugin') -Raw | ConvertFrom-Json
if (-not $descriptor.Installed) { throw 'UAT did not produce an installed/precompiled package.' }
$outputs=@()
$expected=@('Binaries/Win64/UnrealEditor-YesterdaySaveGuard.dll','Binaries/Win64/UnrealEditor.modules',
    'Intermediate/Build/Win64/x64/UnrealEditor/Development/YesterdaySaveGuard/UnrealEditor-YesterdaySaveGuard.lib')
foreach ($config in @('Development','Shipping')) {
    $prefix='Intermediate/Build/Win64/x64/UnrealGame/'+$config+'/YesterdaySaveGuard/'
    $expected += $prefix+'YesterdaySaveGuard.precompiled'
    foreach ($name in @('Module.YesterdaySaveGuard.cpp.obj','YesterdaySaveGuardLibrary.cpp.obj','YesterdaySaveGuardModule.cpp.obj')) { $expected += $prefix+$name }
    $precompiled=Get-Content -LiteralPath (Join-Path $package ($prefix+'YesterdaySaveGuard.precompiled')) -Raw | ConvertFrom-Json
    if (@($precompiled.OutputFiles).Count -ne 3) { throw 'Unexpected game-config precompiled object list.' }
    foreach ($object in $precompiled.OutputFiles) { if (-not (Test-Path -LiteralPath (Join-Path $package ($prefix+$object)) -PathType Leaf)) { throw 'Precompiled manifest references a missing object.' } }
}
# Android (Meta Quest 3) game-config objects: UBT places them under Intermediate/Build/Android/<arch>/UnrealGame/<config>/
# (or without the architecture folder); every file of each directory is pinned.
$androidDirectories=@()
$androidRoot=Join-Path $package 'Intermediate/Build/Android'
if (-not (Test-Path -LiteralPath $androidRoot -PathType Container)) { throw 'Missing Android plugin build output (Version 5 requires Win64+Android).' }
$androidFiles=@(Get-ChildItem -LiteralPath $androidRoot -File -Recurse)
foreach ($config in @('Development','Shipping')) {
    # UBT writes the game-config manifest at Android/UnrealGame/<config>/ and the objects per architecture
    # at Android/<arch>/UnrealGame/<config>/ (arm64 = 'a'; x64 = 'x' is also produced by BuildPlugin).
    $manifests=@($androidFiles | Where-Object { $_.Name -eq 'YesterdaySaveGuard.precompiled' -and $_.FullName -match ('\\UnrealGame\\'+$config+'\\YesterdaySaveGuard\\') })
    if ($manifests.Count -lt 1) { throw ('Missing Android precompiled manifest for '+$config) }
    $arm64Objects=@($androidFiles | Where-Object { $_.Extension -eq '.o' -and $_.FullName -match ('\\Android\\a\\UnrealGame\\'+$config+'\\YesterdaySaveGuard\\') })
    if ($arm64Objects.Count -lt 3) { throw ('Missing Android arm64 '+$config+' plugin objects') }
    foreach ($object in $arm64Objects) { $androidDirectories += (Split-Path -Parent $object.FullName).Substring($package.Length+1).Replace('\','/') }
}
$androidDirectories=@($androidDirectories | Sort-Object -Unique)
foreach ($file in $androidFiles) { $expected += $file.FullName.Substring($package.Length+1).Replace('\','/') }
foreach ($relative in $expected) {
    $path=Join-Path $package $relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -le 0) { throw ('Missing native output '+$relative) }
    $outputs += [ordered]@{path=$relative;bytes=(Get-Item -LiteralPath $path).Length;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash}
}
$proof=[ordered]@{success=$true;package=$package;build_evidence=$evidenceRoot;engine_build_id=$modules.BuildId;source_matches=$true;source_files=$sourceFiles;outputs=$outputs;descriptor_version=$descriptor.Version;descriptor_installed=$descriptor.Installed;descriptor_platforms=@($descriptor.SupportedTargetPlatforms);target_platforms='Win64+Android';editor_module_compiled_and_linked=$true;game_development_objects_compiled=$true;game_shipping_objects_compiled=$true;android_game_objects_compiled=$true;android_output_directories=$androidDirectories;whole_game_executable_linked=$false;native_fault_tests_verified=$false}
$proof | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidenceRoot 'compiled_module_verification.json') -Encoding utf8
[pscustomobject]$proof | Select-Object success,descriptor_version,engine_build_id,source_matches,editor_module_compiled_and_linked,whole_game_executable_linked | ConvertTo-Json
