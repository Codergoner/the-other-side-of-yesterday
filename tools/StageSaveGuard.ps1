param(
    [Parameter(Mandatory=$true)][string]$Verification,
    [switch]$Stage,
    [switch]$ReplaceExisting
)
$ErrorActionPreference = 'Stop'
$releaseRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if ((Split-Path -Leaf $releaseRoot) -ne 'Release_20261026') { throw 'Staging refuses protected project copies.' }
$projectRoot = Join-Path $releaseRoot 'game_unreal'
$projectFile = Join-Path $projectRoot 'YesterdayHarbor.uproject'
$proof = Get-Content -LiteralPath $Verification -Raw | ConvertFrom-Json
if (-not $proof.success -or -not $proof.source_matches) { throw 'A successful actual compiled-module verification is required.' }
$packageRoot = [IO.Path]::GetFullPath($proof.package)
$descriptorFile = Join-Path $packageRoot 'YesterdaySaveGuard.uplugin'
$descriptor = Get-Content -LiteralPath $descriptorFile -Raw | ConvertFrom-Json
if (-not $descriptor.Installed) { throw 'Use the real BuildPlugin installed/precompiled package.' }
$modules = Get-Content -LiteralPath (Join-Path $packageRoot 'Binaries/Win64/UnrealEditor.modules') -Raw | ConvertFrom-Json
$engineModules = Get-Content -LiteralPath 'C:/Program Files/Epic Games/UE_5.8/Engine/Binaries/Win64/UnrealEditor.modules' -Raw | ConvertFrom-Json
if ($modules.BuildId -ne $engineModules.BuildId -or $modules.BuildId -ne $proof.engine_build_id) { throw 'Compiled plugin/editor BuildId mismatch.' }
foreach ($entry in $proof.outputs) {
    $actual = Join-Path $packageRoot $entry.path
    if (-not (Test-Path -LiteralPath $actual -PathType Leaf) -or (Get-FileHash -LiteralPath $actual -Algorithm SHA256).Hash -ne $entry.sha256) { throw ('Verified build output changed: ' + $entry.path) }
}
$target = [IO.Path]::GetFullPath((Join-Path $projectRoot 'Plugins/YesterdaySaveGuard'))
$allowed = [IO.Path]::GetFullPath((Join-Path $projectRoot 'Plugins')) + [IO.Path]::DirectorySeparatorChar
if (-not $target.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)) { throw 'Resolved plugin target escaped the release Plugins directory.' }
$plan = [ordered]@{ source=$packageRoot; target=$target; verification=[IO.Path]::GetFullPath($Verification); engine_build_id=$modules.BuildId; descriptor_installed=$descriptor.Installed; stage_requested=[bool]$Stage; replace_existing=[bool]$ReplaceExisting; game_executable_linked=$false; policy='Actual verified package only; no receipt fabrication or engine/global config changes. Explicit replacement preserves the prior complete plugin in the activation evidence directory.' }
if (-not $Stage) { $plan | ConvertTo-Json; return }
if (Get-Process UnrealEditor,UnrealEditor-Cmd,blender -ErrorAction SilentlyContinue) { throw 'Root writer queue requires all Unreal/Blender processes exited before plugin activation.' }
if ((Test-Path -LiteralPath $target) -and -not $ReplaceExisting) { throw 'Plugin directory already exists; explicit verified archival replacement is required.' }
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss_fffffff')
$evidence = Join-Path $releaseRoot ('output/save_guard_activation/' + $stamp)
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
Copy-Item -LiteralPath $projectFile -Destination (Join-Path $evidence 'YesterdayHarbor.uproject.before')
if (Test-Path -LiteralPath $target) {
    $resolvedSource = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $target).Path)
    $backupTarget = [IO.Path]::GetFullPath((Join-Path $evidence 'plugin_before'))
    $evidenceBoundary = [IO.Path]::GetFullPath((Join-Path $releaseRoot 'output/save_guard_activation')) + [IO.Path]::DirectorySeparatorChar
    if ($resolvedSource -ne $target -or -not $resolvedSource.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase) -or -not $backupTarget.StartsWith($evidenceBoundary,[StringComparison]::OrdinalIgnoreCase)) { throw 'Verified absolute archive paths escaped the intended release directories.' }
    if ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing to move a plugin junction/reparse point.' }
    $previousManifests = @(Get-ChildItem -LiteralPath (Join-Path $releaseRoot 'output/save_guard_activation') -Filter 'activation.json' -Recurse | Sort-Object LastWriteTime -Descending)
    $prior = $null
    foreach ($manifest in $previousManifests) {
        $candidate = Get-Content -LiteralPath $manifest.FullName -Raw | ConvertFrom-Json
        if ($candidate.target -eq $target -and $candidate.executed) { $prior=$candidate;break }
    }
    if (-not $prior) { throw 'Existing plugin has no recorded owned activation; preserve it for manual review.' }
    foreach ($entry in $prior.files) {
        $oldFile = Join-Path $target $entry.path
        if (-not (Test-Path -LiteralPath $oldFile -PathType Leaf) -or (Get-FileHash -LiteralPath $oldFile -Algorithm SHA256).Hash -ne $entry.sha256) { throw ('Existing plugin differs from its owned activation: ' + $entry.path) }
    }
    # One native PowerShell move end-to-end; absolute source/destination above
    # are verified before this recursive directory operation. No deletion.
    Move-Item -LiteralPath $target -Destination $backupTarget
    $plan.previous_plugin_archive=$backupTarget
}
New-Item -ItemType Directory -Path $target -Force | Out-Null
foreach ($child in Get-ChildItem -LiteralPath $packageRoot -Force) {
    Copy-Item -LiteralPath $child.FullName -Destination $target -Recurse
}
$files = @()
foreach ($sourceFile in Get-ChildItem -LiteralPath $packageRoot -File -Recurse -Force) {
    $relative = $sourceFile.FullName.Substring($packageRoot.TrimEnd('\').Length).TrimStart('\')   # GetRelativePath equivalent; Windows PowerShell 5.1 has no [IO.Path]::GetRelativePath
    $destination = Join-Path $target $relative
    $digest = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash
    if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne $digest) { throw ('Plugin copied bytes differ: ' + $relative) }
    $files += [ordered]@{path=$relative;sha256=$digest;bytes=$sourceFile.Length}
}
$project = Get-Content -LiteralPath $projectFile -Raw | ConvertFrom-Json
$plugins = @($project.Plugins)
$entry = @($plugins | Where-Object Name -eq 'YesterdaySaveGuard')
if ($entry.Count -gt 1) { throw 'Duplicate plugin references require manual review.' }
# Version 5 (2 November 2026): the staged guard supports Win64 and Android (Meta Quest 3); the
# project reference mirrors the descriptor's SupportedTargetPlatforms.
$stagedPlatforms=@($descriptor.SupportedTargetPlatforms)
if ($stagedPlatforms.Count -lt 1) { $stagedPlatforms=@('Win64') }
if ($entry.Count -eq 1) {
    $entry[0].Enabled=$true
    $entry[0] | Add-Member -NotePropertyName SupportedTargetPlatforms -NotePropertyValue $stagedPlatforms -Force
}
else { $plugins += [pscustomobject]@{Name='YesterdaySaveGuard';Enabled=$true;SupportedTargetPlatforms=$stagedPlatforms} }
$project.Plugins=$plugins
[IO.File]::WriteAllText($projectFile,($project | ConvertTo-Json -Depth 20)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
$plan.executed=$true
$plan.files=$files
$plan.project_sha256=(Get-FileHash -LiteralPath $projectFile -Algorithm SHA256).Hash
$plan.native_module_loaded=$false
$plan.graphs_rewired=$false
$plan.fault_tests_passed=$false
$plan | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $evidence 'activation.json') -Encoding utf8
$plan | ConvertTo-Json -Depth 3
