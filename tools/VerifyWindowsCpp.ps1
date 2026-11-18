$ErrorActionPreference = 'Stop'
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$releaseStage = Join-Path $releaseRoot 'output/toolchain_staging'
$releaseVswhere = 'C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe'
$releaseInstances = @((& $releaseVswhere -products '*' -requires Microsoft.VisualStudio.Component.VC.14.44.17.14.x86.x64 -format json | ConvertFrom-Json))
$releaseInstance = @($releaseInstances | Where-Object { $_.isComplete -and $_.isLaunchable -and $_.productId -eq 'Microsoft.VisualStudio.Product.Community' })
if ($releaseInstance.Count -ne 1) { throw 'Expected one complete approved Community installation with the requested compiler.' }
$releaseCompiler = Join-Path $releaseInstance[0].installationPath 'VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe'
$releaseCompilerVersion = [version](Get-Item -LiteralPath $releaseCompiler).VersionInfo.ProductVersion
if ($releaseCompilerVersion -lt [version]'14.44.35211.0' -or $releaseCompilerVersion -ge [version]'14.45.0.0') { throw 'Actual compiler is outside the reviewed UE5.8 preferred non-banned range.' }
$releaseSdkRoot = 'C:/Program Files (x86)/Windows Kits/10'
$releaseSdkHeader = Join-Path $releaseSdkRoot 'Include/10.0.22621.0/um/Windows.h'
$releaseResourceCompiler = Join-Path $releaseSdkRoot 'bin/10.0.22621.0/x64/rc.exe'
if (-not (Test-Path -LiteralPath $releaseSdkHeader) -or -not (Test-Path -LiteralPath $releaseResourceCompiler)) { throw 'Requested Windows SDK header/resource compiler is missing.' }
$releaseNetFx = (Get-ItemProperty -LiteralPath 'HKLM:/SOFTWARE/WOW6432Node/Microsoft/Microsoft SDKs/NETFXSDK/4.8').KitsInstallationFolder
if (-not $releaseNetFx -or -not (Test-Path -LiteralPath (Join-Path $releaseNetFx 'Include/um/metahost.h'))) { throw 'Unreal editor build dependency .NET Framework SDK 4.8 is missing.' }
$releaseResult = [ordered]@{
    success=$true; verified_utc=[DateTime]::UtcNow.ToString('o'); scope='Installed toolchain discovery only; native module compilation is a separate gate'
    installation=$releaseInstance[0]; compiler_path=$releaseCompiler; compiler_product_version=[string]$releaseCompilerVersion
    sdk_version='10.0.22621.0'; sdk_header=$releaseSdkHeader; resource_compiler=$releaseResourceCompiler
    net_framework_sdk='4.8'; net_framework_sdk_path=$releaseNetFx
    engine_requirements='C:/Program Files/Epic Games/UE_5.8/Engine/Config/Windows/Windows_SDK.json'
    automatic_restart_performed=$false
}
$releaseResult | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $releaseStage 'installation_verified.json')
[pscustomobject]$releaseResult | Select-Object success,compiler_product_version,sdk_version,scope | ConvertTo-Json
