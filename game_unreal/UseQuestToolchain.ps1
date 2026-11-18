# Dot-source from this project's build/preflight wrappers. Environment changes
# affect only the current process and children; no registry or user PATH writes.
$questToolchainManifestPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../tools/android_toolchain_manifest.json'))
if (-not (Test-Path -LiteralPath $questToolchainManifestPath)) {
    throw 'Portable toolchain manifest is missing. Run tools/setup_android_toolchain.py first.'
}
$questToolchain = Get-Content -LiteralPath $questToolchainManifestPath -Raw | ConvertFrom-Json
if (-not $questToolchain.success) {
    throw 'Portable toolchain setup has not completed. Inspect tools/android_toolchain_status.json.'
}
foreach ($questDirectory in @($questToolchain.sdk_root, $questToolchain.ndk_root, $questToolchain.java_home)) {
    if (-not (Test-Path -LiteralPath $questDirectory -PathType Container)) { throw "Toolchain directory is missing: $questDirectory" }
}
$env:ANDROID_HOME = $questToolchain.sdk_root
$env:ANDROID_SDK_ROOT = $questToolchain.sdk_root
$env:NDKROOT = $questToolchain.ndk_root
$env:NDK_ROOT = $questToolchain.ndk_root
$env:JAVA_HOME = $questToolchain.java_home
$env:AGDE_JAVA_HOME = $questToolchain.java_home
$env:ANDROID_USER_HOME = Join-Path $questToolchain.install_root 'android-user'
$env:GRADLE_USER_HOME = $questToolchain.gradle_user_home
$env:PATH = (Join-Path $env:JAVA_HOME 'bin') + ';' + (Join-Path $env:ANDROID_HOME 'platform-tools') + ';' + $env:PATH
