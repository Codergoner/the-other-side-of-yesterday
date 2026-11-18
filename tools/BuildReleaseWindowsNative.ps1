param([switch]$Build)
$ErrorActionPreference='Stop'
$releaseRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if ((Split-Path -Leaf $releaseRoot) -ne 'Release_20261026') { throw 'Native release builder refuses protected project copies.' }
$projectRoot=Join-Path $releaseRoot 'game_unreal'
$projectFile=Join-Path $projectRoot 'YesterdayHarbor.uproject'
$engine='C:/Program Files/Epic Games/UE_5.8'
$uat=Join-Path $engine 'Engine/Build/BatchFiles/RunUAT.bat'
$editor=Join-Path $engine 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
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
    if (-not $descriptor.Installed -or $descriptor.Version -lt 2) { $blockers += 'A verified installed CNG-v2-or-newer plugin is required.' }
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
    $engineModules=Get-Content -LiteralPath (Join-Path $engine 'Engine/Binaries/Win64/UnrealEditor.modules') -Raw | ConvertFrom-Json
    if ($proof.engine_build_id -ne $engineModules.BuildId) { $blockers += 'Compiled native-plugin ABI differs from the installed engine.' }
    foreach ($entry in $proof.outputs) {
        $nativeFile=Join-Path $plugin $entry.path
        if (-not (Test-Path -LiteralPath $nativeFile -PathType Leaf) -or (Get-FileHash -LiteralPath $nativeFile -Algorithm SHA256).Hash -ne $entry.sha256) { $blockers += ('Activated output differs from actual compilation: '+$entry.path) }
    }
}
$project=Get-Content -LiteralPath $projectFile -Raw | ConvertFrom-Json
if (@($project.Plugins | Where-Object { $_.Name -eq 'YesterdaySaveGuard' -and $_.Enabled }).Count -ne 1) { $blockers += 'Release descriptor must explicitly enable the actual native guard.' }
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
$plan=[ordered]@{ready=($blockers.Count -eq 0);blockers=$blockers;scope='Fresh short manifest-verified snapshot, real Win64 Shipping build/link/cook/archive; not the old skipbuild wrapper.';build_requested=[bool]$Build;native_game_linked=$false;package_playtested=$false;global_path_policy_changes=$false;copies_root_caches_or_player_saves=$false;preserves_plugin_precompiled_intermediate=$true}
if (-not $Build) { $plan | ConvertTo-Json -Depth 4;return }
if ($blockers.Count) { throw ($blockers -join [Environment]::NewLine) }
if (Get-Process UnrealEditor,UnrealEditor-Cmd,blender -ErrorAction SilentlyContinue) { throw 'Freeze all native asset writers/readers before taking the final package snapshot.' }
& (Join-Path $PSScriptRoot 'VerifyWindowsCpp.ps1') | Out-Null
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmss_fffffff')
$shortRoot=Join-Path $env:LOCALAPPDATA ('TOSOYBuild/Release/'+$stamp)
$snapshot=Join-Path $shortRoot 'game'
$evidence=Join-Path $releaseRoot ('output/windows_native_builds/'+$stamp)
$archive=Join-Path $evidence 'archive'
if (Test-Path -LiteralPath $shortRoot) { throw 'A new nonoccupied build snapshot is required.' }
New-Item -ItemType Directory -Path $snapshot -Force | Out-Null
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$inputs=@(Get-Item -LiteralPath $projectFile)
# Exclude only top-level generated state. Plugin Intermediate and Binaries are
# genuine verified BuildPlugin products and must NOT be glob-excluded.
foreach ($folder in @('Content','Config','Plugins','Source','Shaders','Build','ContentData')) {
    $inputRoot=Join-Path $projectRoot $folder
    if (Test-Path -LiteralPath $inputRoot -PathType Container) { $inputs += @(Get-ChildItem -LiteralPath $inputRoot -File -Recurse -Force) }
}
# Some release inputs (character unit-probe assets) exceed MAX_PATH. Windows PowerShell 5.1's
# Get-FileHash/Copy-Item/Test-Path cannot open them, but .NET extended-length paths can; no OS path
# policy is changed. These helpers are used for every input so one code path handles all of them.
function Get-ExtendedPath([string]$path) { if ($path.StartsWith('\\?\')) { $path } elseif ($path.StartsWith('\\')) { '\\?\UNC\'+$path.Substring(2) } else { '\\?\'+$path } }
function Get-FileSha256Long([string]$path) {
    $stream=[IO.File]::OpenRead((Get-ExtendedPath $path))
    try { $algorithm=[Security.Cryptography.SHA256]::Create(); return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','') }
    finally { $stream.Dispose() }
}
function Test-FileLong([string]$path) { return [IO.File]::Exists((Get-ExtendedPath $path)) }
$manifest=@()
foreach ($releaseInput in $inputs) {
    $relative=$releaseInput.FullName.Substring($projectRoot.TrimEnd('\').Length).TrimStart('\')   # GetRelativePath equivalent; Windows PowerShell 5.1 has no [IO.Path]::GetRelativePath
    $destination=[IO.Path]::GetFullPath((Join-Path $snapshot $relative))
    if (-not $destination.StartsWith($snapshot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Snapshot input escaped its fresh short directory.' }
    $hash=Get-FileSha256Long $releaseInput.FullName
    [IO.Directory]::CreateDirectory((Get-ExtendedPath (Split-Path -Parent $destination))) | Out-Null
    [IO.File]::Copy((Get-ExtendedPath $releaseInput.FullName),(Get-ExtendedPath $destination),$false)
    if ((Get-FileSha256Long $destination) -ne $hash) { throw ('Snapshot byte mismatch: '+$relative) }
    $manifest += [ordered]@{relative=$relative;source=$releaseInput.FullName;copy=$destination;bytes=([IO.FileInfo]::new((Get-ExtendedPath $releaseInput.FullName))).Length;sha256=$hash}
}
$precompiled=@($manifest | Where-Object { $_.relative -like 'Plugins*YesterdaySaveGuard*Intermediate*.precompiled' })
if ($precompiled.Count -lt 2) { throw 'Snapshot lost the actual guard game-config precompiled manifests.' }
$totalBytes=[int64]0
foreach ($entry in $manifest) { $totalBytes += [int64]$entry.bytes }   # Measure-Object cannot sum a hashtable key in Windows PowerShell 5.1
$frozen=[ordered]@{created_utc=[DateTime]::UtcNow.ToString('o');source=$projectRoot;snapshot=$snapshot;files=$manifest;file_count=$manifest.Count;total_bytes=$totalBytes;plugin_precompiled_manifests=$precompiled.Count;copies_top_level_saved=$false;copies_top_level_intermediate=$false;copies_top_level_binaries=$false}
$frozen | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidence 'snapshot_manifest.json') -Encoding utf8
$targetProject=(Join-Path $snapshot 'YesterdayHarbor.uproject').Replace('\','/')
$log=Join-Path $evidence 'build.log'
$start=[DateTime]::UtcNow
# No -skipbuild, -skipbuildclient, -nocompile, copied stock receipt or fabricated
# target. UAT/UBT must create/link the actual native game in this fresh snapshot.
& $uat BuildCookRun "-project=$targetProject" "-unrealexe=$editor" -installed -nop4 -unattended -utf8output -noautosdk -noturnkeyvariables -platform=Win64 -clientconfig=Shipping -build -cook -map=/Game/Quest/Maps/Verdant_Desktop -stage -pak -iostore -compressed -package -archive "-archivedirectory=$archive" -nodebuginfo -prereqs 2>&1 | Tee-Object -FilePath $log
$exit=$LASTEXITCODE
$sourceStable=$true
foreach ($entry in $manifest) { if (-not (Test-FileLong $entry.source) -or (Get-FileSha256Long $entry.source) -ne $entry.sha256) { $sourceStable=$false } }
$nativeExes=@(Get-ChildItem -LiteralPath (Join-Path $snapshot 'Binaries') -Filter '*-Win64-Shipping.exe' -File -Recurse -ErrorAction SilentlyContinue)
$buildText=Get-Content -LiteralPath $log -Raw
$actualLink=($nativeExes.Count -gt 0) -and ($buildText -match 'Link\s+\[x64\].*Shipping\.exe')
$archived=@(Get-ChildItem -LiteralPath $archive -Filter '*.exe' -File -Recurse -ErrorAction SilentlyContinue)
$result=[ordered]@{success=($exit -eq 0 -and $sourceStable -and $actualLink -and $archived.Count -gt 0);uat_exit_code=$exit;native_game_executable_link_evidence=$actualLink;source_inputs_unchanged=$sourceStable;source_snapshot=$snapshot;archive=$archive;elapsed_seconds=([DateTime]::UtcNow-$start).TotalSeconds;native_game_executables=@($nativeExes | ForEach-Object {$_.FullName});archived_executables=@($archived | ForEach-Object {$_.FullName});package_playtested=$false;trailer_captured=$false;proof_scope='Actual build/link/cook/archive only. Fresh-user standalone gameplay, corruption recovery, audio playback/performance and trailer remain separate tests.'}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'build_result.json') -Encoding utf8
$result | ConvertTo-Json -Depth 4
if (-not $result.success) { throw ('Native Windows build gate failed; inspect '+$evidence) }
