param([switch]$Install, [switch]$CompleteNetFx)
$ErrorActionPreference = 'Stop'
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$releaseStage = Join-Path $releaseRoot 'output/toolchain_staging'
$releaseProvenance = Get-Content -LiteralPath (Join-Path $releaseStage 'installer_provenance.json') -Raw | ConvertFrom-Json
$releaseInstaller = Join-Path $releaseStage 'vs_community_2022.exe'
$releaseSignature = Get-AuthenticodeSignature -LiteralPath $releaseInstaller
if ($releaseSignature.Status -ne 'Valid' -or $releaseSignature.SignerCertificate.Subject -notlike '*Microsoft Corporation*') { throw 'Installer signature is not the verified Microsoft signature.' }
if ((Get-FileHash -LiteralPath $releaseInstaller -Algorithm SHA256).Hash -ne $releaseProvenance.sha256) { throw 'Installer changed since the reviewed download.' }
$releaseArguments = '--passive --norestart --wait --installPath "C:\Program Files\Microsoft Visual Studio\2022\Community" --add Microsoft.VisualStudio.Component.VC.14.44.17.14.x86.x64 --add Microsoft.VisualStudio.Component.Windows11SDK.22621'
if ($CompleteNetFx) {
    # The first actual UE5.8 BuildPlugin attempt identified this editor dependency.
    # ID verified against the installed Microsoft instance's catalog.json.
    $releaseArguments = 'modify --passive --norestart --wait --installPath "C:\Program Files\Microsoft Visual Studio\2022\Community" --add Microsoft.Net.Component.4.8.SDK'
}
$releasePlan = [ordered]@{product='Microsoft Visual Studio Community 2022';source=$releaseProvenance.source;signature_status=[string]$releaseSignature.Status;sha256=$releaseProvenance.sha256;components=@('MSVC v143 14.44 x64/x86','Windows 11 SDK 10.0.22621.0');additional_extensions=@();arguments=$releaseArguments;automatic_restart=$false;scope='Additional Windows C++ toolchain; separate from previously approved Android tools';executed=$false}
if ($CompleteNetFx) { $releasePlan.components = @('.NET Framework 4.8 SDK'); $releasePlan.scope = 'Required Unreal editor compile dependency identified by actual native build failure' }
if (-not $Install) {
    $releasePlan | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $releaseStage 'installation_plan.json')
    $releasePlan | ConvertTo-Json -Depth 3
    return
}
# Root may use -Install only after the human approves this specific new setup.
# Windows may present an elevation prompt; it must be handled by the user.
$releaseSetup = Start-Process -FilePath $releaseInstaller -ArgumentList $releaseArguments -WindowStyle Hidden -PassThru
$releasePlan.executed = $true
$releasePlan.pid = $releaseSetup.Id
$releasePlan.started_utc = [DateTime]::UtcNow.ToString('o')
$releaseStartedName = if ($CompleteNetFx) { 'installation_netfx_started.json' } else { 'installation_started.json' }
$releasePlan | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $releaseStage $releaseStartedName)
Write-Output ('C++ setup started, PID ' + $releaseSetup.Id + '. Verify actual installed compiler/SDK before building; no restart was requested.')
