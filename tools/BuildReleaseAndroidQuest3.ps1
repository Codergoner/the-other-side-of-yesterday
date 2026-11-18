param(
    [switch]$Build,
    [ValidateSet('Shipping','Development')][string]$Configuration='Shipping',
    [switch]$AllowUnvalidatedXR
)
# Meta Quest 3 (Android ARM64 / Vulkan / ASTC) package of the Release copy, with the same evidence
# discipline as BuildReleaseWindowsNative.ps1: native gates, fresh short manifest-verified snapshot,
# real UAT build/cook/stage/pak/package/archive, APK inspection, package fingerprint, protected
# sources re-verified. Windows PowerShell 5.1. Added 2 November 2026 (recorded platform change).
$ErrorActionPreference='Stop'
$releaseRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if ((Split-Path -Leaf $releaseRoot) -ne 'Release_20261026') { throw 'Quest 3 release builder refuses protected project copies.' }
$projectRoot=Join-Path $releaseRoot 'game_unreal'
$projectFile=Join-Path $projectRoot 'YesterdayHarbor.uproject'
$engine='C:/Program Files/Epic Games/UE_5.8'
$uat=Join-Path $engine 'Engine/Build/BatchFiles/RunUAT.bat'
$editor=Join-Path $engine 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
$blenderPython='C:/Program Files/Blender Foundation/Blender 5.2/5.2/python/bin/python.exe'
. (Join-Path $projectRoot 'UseQuestToolchain.ps1')
$blockers=@()
foreach ($name in @('release_save_guard_integration.json','release_save_guard_validation.json','release_save_guard_ui_validation.json')) {
    $path=Join-Path $projectRoot $name
    if (-not (Test-Path -LiteralPath $path)) { $blockers += ('Missing native gate '+$name);continue }
    $gate=Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    if (-not $gate.success) { $blockers += ('Native gate has not passed: '+$name) }
}
$plugin=Join-Path $projectRoot 'Plugins/YesterdaySaveGuard'
$descriptorFile=Join-Path $plugin 'YesterdaySaveGuard.uplugin'
if (-not (Test-Path -LiteralPath $descriptorFile)) { $blockers += 'Verified compiled plugin is not activated.' }
else {
    $descriptor=Get-Content -LiteralPath $descriptorFile -Raw | ConvertFrom-Json
    if (-not $descriptor.Installed -or $descriptor.Version -lt 5) { $blockers += 'A verified installed Version 5 (Win64+Android) guard is required.' }
    if (@($descriptor.SupportedTargetPlatforms) -notcontains 'Android') { $blockers += 'Staged guard descriptor does not support Android.' }
    if (@($descriptor.Modules[0].PlatformAllowList) -notcontains 'Android') { $blockers += 'Staged guard module does not allow Android.' }
}
$activation=$null
foreach ($record in @(Get-ChildItem -LiteralPath (Join-Path $releaseRoot 'output/save_guard_activation') -Filter 'activation.json' -Recurse -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)) {
    $candidate=Get-Content -LiteralPath $record.FullName -Raw | ConvertFrom-Json
    if ($candidate.executed -and [IO.Path]::GetFullPath($candidate.target) -eq [IO.Path]::GetFullPath($plugin)) { $activation=$candidate;break }
}
if (-not $activation) { $blockers += 'No actual verified native-plugin activation manifest exists.' }
else {
    foreach ($entry in $activation.files) {
        $nativeFile=Join-Path $plugin $entry.path
        if (-not (Test-Path -LiteralPath $nativeFile -PathType Leaf) -or (Get-FileHash -LiteralPath $nativeFile -Algorithm SHA256).Hash -ne $entry.sha256) { $blockers += ('Activated native plugin changed: '+$entry.path) }
    }
    $proof=Get-Content -LiteralPath $activation.verification -Raw | ConvertFrom-Json
    if (-not $proof.success -or -not $proof.editor_module_compiled_and_linked -or -not $proof.game_shipping_objects_compiled) { $blockers += 'Actual native-plugin compilation proof is incomplete.' }
    if (-not $proof.android_game_objects_compiled) { $blockers += 'The staged guard was not compiled for Android through the chain.' }
    $engineModules=Get-Content -LiteralPath (Join-Path $engine 'Engine/Binaries/Win64/UnrealEditor.modules') -Raw | ConvertFrom-Json
    if ($proof.engine_build_id -ne $engineModules.BuildId) { $blockers += 'Compiled native-plugin ABI differs from the installed engine.' }
    foreach ($entry in $proof.outputs) {
        $nativeFile=Join-Path $plugin $entry.path
        if (-not (Test-Path -LiteralPath $nativeFile -PathType Leaf) -or (Get-FileHash -LiteralPath $nativeFile -Algorithm SHA256).Hash -ne $entry.sha256) { $blockers += ('Activated output differs from actual compilation: '+$entry.path) }
    }
}
$project=Get-Content -LiteralPath $projectFile -Raw | ConvertFrom-Json
$guardEntry=@($project.Plugins | Where-Object { $_.Name -eq 'YesterdaySaveGuard' -and $_.Enabled })
if ($guardEntry.Count -ne 1) { $blockers += 'Release descriptor must explicitly enable the actual native guard.' }
elseif (@($guardEntry[0].SupportedTargetPlatforms) -notcontains 'Android') { $blockers += 'Release descriptor guard reference does not list Android.' }
$openxr=@($project.Plugins | Where-Object { $_.Name -eq 'OpenXR' -and $_.Enabled })
if ($openxr.Count -ne 1 -or ($openxr[0].PlatformAllowList -and @($openxr[0].PlatformAllowList) -notcontains 'Android')) { $blockers += 'OpenXR must be enabled for Android in the release descriptor.' }
if (@($project.Plugins | Where-Object { $_.Name -eq 'XRBase' -and $_.Enabled }).Count -ne 1) { $blockers += 'XRBase must be enabled so the XR pawn compiles on the cook host.' }
if (@($project.TargetPlatforms) -notcontains 'Android') { $blockers += 'Release descriptor TargetPlatforms must include Android.' }
$integrationPath=Join-Path $projectRoot 'release_save_guard_integration.json'
if (Test-Path -LiteralPath $integrationPath) {
    $integration=Get-Content -LiteralPath $integrationPath -Raw | ConvertFrom-Json
    $finalAuditPath=Join-Path $projectRoot 'release_save_guard_final_audit.json'
    if (Test-Path -LiteralPath $finalAuditPath) {
        $finalAudit=Get-Content -LiteralPath $finalAuditPath -Raw | ConvertFrom-Json
        if (-not $finalAudit.success -or -not $finalAudit.original13_node_guids_members_pins_preserved -or $finalAudit.generic_save_calls -ne 0 -or $finalAudit.original_integration_sha256 -ne (Get-FileHash -LiteralPath $integrationPath -Algorithm SHA256).Hash) { $blockers += 'Final save-owner audit is incomplete or refers to another original integration.' }
        else { $integration=$finalAudit }
    }
    $manager=Join-Path $projectRoot 'Content/Opening/Blueprints/BP_OpeningActions.uasset'
    if (-not $integration.manager_asset_sha256 -or (Get-FileHash -LiteralPath $manager -Algorithm SHA256).Hash -ne $integration.manager_asset_sha256) { $blockers += 'Manager changed since the guarded library-owner audit; rerun the bounded integration/audit after the final writer.' }
}
$keyValidationPath=Join-Path $projectRoot 'release_key_literal_persistence_validation.json'
if (-not (Test-Path -LiteralPath $keyValidationPath)) { $blockers += 'Fresh-process keyboard/photo literal persistence proof is required.' }
else {
    $keyValidation=Get-Content -LiteralPath $keyValidationPath -Raw | ConvertFrom-Json
    $keyManager=Join-Path $projectRoot 'Content/Opening/Blueprints/BP_OpeningActions.uasset'
    if (-not $keyValidation.success -or -not $keyValidation.fresh_process_reader_verified -or -not $keyValidation.all49_saved_values_and_guids_match_pinned_full_comparison -or $keyValidation.verified_key_defaults -ne 47 -or $keyValidation.verified_photo_rotation_defaults -ne 2 -or $keyValidation.manager_asset_sha256 -ne (Get-FileHash -LiteralPath $keyManager -Algorithm SHA256).Hash) { $blockers += 'Saved keyboard/photo values do not match the actual current manager.' }
}
# Android / Quest 3 gates
$toolchainManifest=Join-Path $releaseRoot 'tools/android_toolchain_manifest.json'
$toolchain=Get-Content -LiteralPath $toolchainManifest -Raw | ConvertFrom-Json
if (-not $toolchain.success) { $blockers += 'Portable Android toolchain manifest is not successful.' }
foreach ($directory in @($toolchain.sdk_root,$toolchain.ndk_root,$toolchain.java_home)) { if (-not (Test-Path -LiteralPath $directory -PathType Container)) { $blockers += ('Toolchain directory missing: '+$directory) } }
$adb=Join-Path $toolchain.sdk_root 'platform-tools/adb.exe'
if (-not (Test-Path -LiteralPath $adb -PathType Leaf)) { $blockers += 'adb is missing from the portable toolchain.' }
$androidIni=Join-Path $projectRoot 'Config/Android/AndroidEngine.ini'
if (-not (Test-Path -LiteralPath $androidIni -PathType Leaf)) { $blockers += 'Config/Android/AndroidEngine.ini (recorded platform change) is missing.' }
else {
    $androidText=Get-Content -LiteralPath $androidIni -Raw
    foreach ($required in @('PackageName=com.yesterdayharbor.quest3','bPackageForMetaQuest=True','bPackageForOpenXRImmersive=True','bSupportsVulkan=True','bBuildForArm64=True','bBuildForES31=False','MinSDKVersion=32','TargetSDKVersion=36','bPackageDataInsideApk=True')) {
        if ($androidText -notmatch [regex]::Escape($required)) { $blockers += ('AndroidEngine.ini lacks '+$required) }
    }
}
$profilesIni=Join-Path $projectRoot 'Config/DefaultDeviceProfiles.ini'
if (-not (Test-Path -LiteralPath $profilesIni -PathType Leaf) -or (Get-Content -LiteralPath $profilesIni -Raw) -notmatch '\[Meta_Quest_3 DeviceProfile\]') { $blockers += 'Headset rendering profile [Meta_Quest_3 DeviceProfile] is missing.' }
$xrValidationPath=Join-Path $projectRoot 'quest3_xr_runtime_validation.json'
$xrValidated=$false
if (Test-Path -LiteralPath $xrValidationPath) { $xrValidated=[bool](Get-Content -LiteralPath $xrValidationPath -Raw | ConvertFrom-Json).success }
if (-not $xrValidated -and -not $AllowUnvalidatedXR) { $blockers += 'XR adapter runtime validation (quest3_xr_runtime_validation.json) has not passed; pass -AllowUnvalidatedXR only for a profiling build and record it.' }
$plan=[ordered]@{ready=($blockers.Count -eq 0);blockers=$blockers;configuration=$Configuration;scope='Fresh short manifest-verified snapshot, real Android ARM64 Vulkan ASTC build/cook/stage/pak/package/archive through UAT; APK inspected; not device-tested by this script.';build_requested=[bool]$Build;xr_adapters_validated=$xrValidated;xr_validation_overridden=[bool]($AllowUnvalidatedXR -and -not $xrValidated);global_path_policy_changes=$false;global_environment_changes=$false;copies_root_caches_or_player_saves=$false}
if (-not $Build) { $plan | ConvertTo-Json -Depth 4;return }
if ($blockers.Count) { throw ($blockers -join [Environment]::NewLine) }
if (Get-Process UnrealEditor,UnrealEditor-Cmd,blender -ErrorAction SilentlyContinue) { throw 'Freeze all native asset writers/readers before taking the final package snapshot.' }
& (Join-Path $PSScriptRoot 'VerifyWindowsCpp.ps1') | Out-Null
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmss_fffffff')
$shortRoot=Join-Path $env:LOCALAPPDATA ('TOSOYBuild/Quest3/'+$stamp)
$snapshot=Join-Path $shortRoot 'game'
$evidence=Join-Path $releaseRoot ('output/quest3_builds/'+$stamp)
$archive=Join-Path $evidence 'archive'
if (Test-Path -LiteralPath $shortRoot) { throw 'A new nonoccupied build snapshot is required.' }
New-Item -ItemType Directory -Path $snapshot -Force | Out-Null
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$inputs=@(Get-Item -LiteralPath $projectFile)
foreach ($folder in @('Content','Config','Plugins','Source','Shaders','Build','ContentData')) {
    $inputRoot=Join-Path $projectRoot $folder
    if (Test-Path -LiteralPath $inputRoot -PathType Container) { $inputs += @(Get-ChildItem -LiteralPath $inputRoot -File -Recurse -Force) }
}
function Get-ExtendedPath([string]$path) { if ($path.StartsWith('\\?\')) { $path } elseif ($path.StartsWith('\\')) { '\\?\UNC\'+$path.Substring(2) } else { '\\?\'+$path } }
function Get-FileSha256Long([string]$path) {
    $stream=[IO.File]::OpenRead((Get-ExtendedPath $path))
    try { $algorithm=[Security.Cryptography.SHA256]::Create(); return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','') }
    finally { $stream.Dispose() }
}
function Test-FileLong([string]$path) { return [IO.File]::Exists((Get-ExtendedPath $path)) }
$manifest=@()
foreach ($releaseInput in $inputs) {
    $relative=$releaseInput.FullName.Substring($projectRoot.TrimEnd('\').Length).TrimStart('\')
    $destination=[IO.Path]::GetFullPath((Join-Path $snapshot $relative))
    if (-not $destination.StartsWith($snapshot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Snapshot input escaped its fresh short directory.' }
    $hash=Get-FileSha256Long $releaseInput.FullName
    [IO.Directory]::CreateDirectory((Get-ExtendedPath (Split-Path -Parent $destination))) | Out-Null
    [IO.File]::Copy((Get-ExtendedPath $releaseInput.FullName),(Get-ExtendedPath $destination),$false)
    if ((Get-FileSha256Long $destination) -ne $hash) { throw ('Snapshot byte mismatch: '+$relative) }
    $manifest += [ordered]@{relative=$relative;source=$releaseInput.FullName;copy=$destination;bytes=([IO.FileInfo]::new((Get-ExtendedPath $releaseInput.FullName))).Length;sha256=$hash}
}
$precompiled=@($manifest | Where-Object { $_.relative -like 'Plugins*YesterdaySaveGuard*Intermediate*.precompiled' })
if ($precompiled.Count -lt 4) { throw 'Snapshot lost the guard precompiled manifests (Win64 and Android game configs).' }
$totalBytes=[int64]0
foreach ($entry in $manifest) { $totalBytes += [int64]$entry.bytes }
$managerEntry=@($manifest | Where-Object { $_.relative -eq 'Content\Opening\Blueprints\BP_OpeningActions.uasset' })
$frozen=[ordered]@{created_utc=[DateTime]::UtcNow.ToString('o');source=$projectRoot;snapshot=$snapshot;files=$manifest;file_count=$manifest.Count;total_bytes=$totalBytes;plugin_precompiled_manifests=$precompiled.Count;snapshot_manager_sha256=$(if ($managerEntry.Count -eq 1) { $managerEntry[0].sha256 } else { $null });copies_top_level_saved=$false;copies_top_level_intermediate=$false;copies_top_level_binaries=$false}
$frozen | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidence 'snapshot_manifest.json') -Encoding utf8
$targetProject=(Join-Path $snapshot 'YesterdayHarbor.uproject').Replace('\','/')
$log=Join-Path $evidence 'build.log'
$start=[DateTime]::UtcNow
$uatArguments=@('BuildCookRun',"-project=$targetProject","-unrealexe=$editor",'-installed','-nop4','-unattended','-utf8output','-noautosdk','-noturnkeyvariables','-platform=Android','-cookflavor=ASTC',"-clientconfig=$Configuration",'-build','-cook','-map=/Game/Quest/Maps/Verdant_Desktop','-stage','-pak','-compressed','-package','-archive',"-archivedirectory=$archive")
if ($Configuration -eq 'Shipping') { $uatArguments += '-nodebuginfo' }
& $uat @uatArguments 2>&1 | Tee-Object -FilePath $log
$exit=$LASTEXITCODE
$sourceStable=$true
foreach ($entry in $manifest) { if (-not (Test-FileLong $entry.source) -or (Get-FileSha256Long $entry.source) -ne $entry.sha256) { $sourceStable=$false } }
$nativeLibraries=@(Get-ChildItem -LiteralPath (Join-Path $snapshot 'Binaries') -Filter '*-arm64.so' -File -Recurse -ErrorAction SilentlyContinue)
$buildText=Get-Content -LiteralPath $log -Raw
$actualLink=($nativeLibraries.Count -gt 0) -and ($buildText -match 'YesterdayHarbor-Android-'+$Configuration+'-arm64|YesterdayHarbor-arm64\.so|libUnreal\.so')
$apks=@(Get-ChildItem -LiteralPath $archive -Filter '*.apk' -File -Recurse -ErrorAction SilentlyContinue)
$apkReport=$null
$apkVerified=$false
if ($apks.Count -eq 1) {
    $apkJson=Join-Path $evidence 'apk_manifest.json'
    & $blenderPython -I (Join-Path $PSScriptRoot 'verify_quest3_apk.py') --apk $apks[0].FullName --output $apkJson --configuration $Configuration | Out-Null
    if (Test-Path -LiteralPath $apkJson) { $apkReport=Get-Content -LiteralPath $apkJson -Raw | ConvertFrom-Json; $apkVerified=[bool]$apkReport.success }
}
$fingerprintRows=@()
$packageFiles=@(Get-ChildItem -LiteralPath $archive -File -Recurse -ErrorAction SilentlyContinue | Sort-Object FullName)
$lines=New-Object System.Text.StringBuilder
foreach ($file in $packageFiles) {
    $relative=$file.FullName.Substring($archive.Length+1).Replace('\','/')
    $digest=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLower()
    $fingerprintRows += [ordered]@{path=$relative;bytes=$file.Length;sha256=$digest}
    [void]$lines.Append($relative+"`t"+$digest+"`t"+$file.Length+"`n")
}
$fingerprint=([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($lines.ToString())))).Replace('-','').ToLower()
[ordered]@{method='SHA-256 over the UTF-8 lines "<relative path>\t<sha256 lower>\t<bytes>\n" of every archived file sorted by full path';archive=$archive;file_count=$packageFiles.Count;files=$fingerprintRows;fingerprint=$fingerprint} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'package_fingerprint.json') -Encoding utf8
& $blenderPython -I (Join-Path $PSScriptRoot 'verify_release_sources.py') | Out-Null
$protectedExit=$LASTEXITCODE
Copy-Item -LiteralPath (Join-Path $releaseRoot 'release_preservation_validation.json') -Destination (Join-Path $evidence 'protected_sources_after_build.json')
$result=[ordered]@{success=($exit -eq 0 -and $sourceStable -and $actualLink -and $apks.Count -eq 1 -and $apkVerified -and $protectedExit -eq 0);configuration=$Configuration;platform='Android ARM64 Vulkan ASTC (Meta Quest 3)';uat_exit_code=$exit;native_library_link_evidence=$actualLink;source_inputs_unchanged=$sourceStable;protected_sources_unchanged=($protectedExit -eq 0);source_snapshot=$snapshot;archive=$archive;elapsed_seconds=([DateTime]::UtcNow-$start).TotalSeconds;native_libraries=@($nativeLibraries | ForEach-Object {$_.FullName});apks=@($apks | ForEach-Object {$_.FullName});apk_sha256=$(if ($apkReport) { $apkReport.sha256 } else { $null });apk_bytes=$(if ($apkReport) { $apkReport.bytes } else { $null });package_fingerprint=$fingerprint;xr_adapters_validated=$xrValidated;xr_validation_overridden=[bool]($AllowUnvalidatedXR -and -not $xrValidated);device_installed=$false;device_tested=$false;proof_scope='Actual build/link/cook/package/archive and APK inspection only. Installation, launch, menus, routes, saves, comfort and frame time on the Quest 3 are separate device tests.'}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'build_result.json') -Encoding utf8
$result | ConvertTo-Json -Depth 4
if (-not $result.success) { throw ('Quest 3 Android build gate failed; inspect '+$evidence) }
