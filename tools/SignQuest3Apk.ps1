param(
    [Parameter(Mandatory=$true)][string]$Apk,
    [Parameter(Mandatory=$true)][string]$Keystore,
    [Parameter(Mandatory=$true)][string]$Alias,
    [string]$Output = ''
)
# Re-signs a Quest 3 APK built by tools/BuildReleaseAndroidQuest3.ps1 with YOUR release keystore (v1 + v2 schemes, as Meta's
# "Android Application Signing" page asks) and verifies the result. Run it yourself in a normal PowerShell window.
#
# This script never creates a key and never sees a password: apksigner asks for the keystore password (and the key password
# if it differs) in the console. Nothing secret is written to disk, to the repository or to the evidence file.
# Create the keystore yourself first (docs/COMPETITION_SIGNING.md step 1) and keep it, with its passwords, somewhere safe:
# every later update of the app must be signed with the same key.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$tools = 'C:\Users\USER\TOSOYQuestToolchain'
$apksigner = Join-Path $tools 'sdk\build-tools\36.0.0\apksigner.bat'
$javaHome = Get-ChildItem (Join-Path $tools 'jdk') -Directory | Select-Object -First 1
if (-not (Test-Path -LiteralPath $apksigner)) { throw "apksigner not found at $apksigner" }
if (-not $javaHome) { throw 'The portable JDK is missing' }
$env:JAVA_HOME = $javaHome.FullName
$apkFile = (Resolve-Path -LiteralPath $Apk).Path
$ksFile = (Resolve-Path -LiteralPath $Keystore).Path
if ($ksFile.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep the keystore outside the project folder (it is synced by OneDrive and must never be committed or shared).'
}
if (-not $Output) { $Output = [IO.Path]::Combine((Split-Path -Parent $apkFile), ([IO.Path]::GetFileNameWithoutExtension($apkFile) + '-release-signed.apk')) }
Copy-Item -LiteralPath $apkFile -Destination $Output -Force
Write-Output "Signing a copy: $Output"
Write-Output 'apksigner will now ask for the keystore password in this window.'
& $apksigner sign --ks $ksFile --ks-key-alias $Alias --v1-signing-enabled true --v2-signing-enabled true $Output
if ($LASTEXITCODE -ne 0) { throw "apksigner sign failed ($LASTEXITCODE)" }
$verify = & $apksigner verify --verbose --print-certs $Output | Out-String
if ($LASTEXITCODE -ne 0) { throw "apksigner verify failed ($LASTEXITCODE)`n$verify" }
$sha = (Get-FileHash -LiteralPath $Output -Algorithm SHA256).Hash.ToLowerInvariant()
$debug = $verify -match 'Android Debug'
$record = [ordered]@{
    signed_apk = $Output; sha256 = $sha; bytes = (Get-Item -LiteralPath $Output).Length
    source_apk = $apkFile; source_sha256 = (Get-FileHash -LiteralPath $apkFile -Algorithm SHA256).Hash.ToLowerInvariant()
    v1_verified = [bool]($verify -match 'v1 scheme \(JAR signing\): true'); v2_verified = [bool]($verify -match 'v2 scheme \(APK Signature Scheme v2\): true')
    signed_with_android_debug_certificate = [bool]$debug
    signer_lines = @($verify -split "`r?`n" | Where-Object { $_ -match 'certificate (DN|SHA-256 digest)' })
    note = 'Signed locally by the entrant. No passwords are recorded here.'
}
$sidecar = [IO.Path]::ChangeExtension($Output, 'signing.json')
$record | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $sidecar -Encoding utf8
$record | ConvertTo-Json -Depth 4
if ($debug) { throw 'The signed APK still shows the Android Debug certificate; use your own release keystore.' }
Write-Output "Done. Upload this file: $Output"
