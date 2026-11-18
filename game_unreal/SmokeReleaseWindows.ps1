param([string]$ArchiveDirectory = (Join-Path $PSScriptRoot '../output/windows_m0_probe'))
$ErrorActionPreference = 'Stop'
$releaseArchive = [IO.Path]::GetFullPath($ArchiveDirectory)
if (-not (Test-Path -LiteralPath (Join-Path $releaseArchive 'YesterdayHarbor.exe'))) { $releaseArchive = Join-Path $releaseArchive 'Windows' }
$releaseBootstrap = Join-Path $releaseArchive 'YesterdayHarbor.exe'
$releaseRuntime = Join-Path $releaseArchive 'Engine/Binaries/Win64/UnrealGame-Win64-Shipping.exe'
if (-not (Test-Path -LiteralPath $releaseBootstrap) -or -not (Test-Path -LiteralPath $releaseRuntime)) { throw 'A real packaged bootstrap and native Shipping runtime are required.' }
$releaseStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss_fffffff')
$releaseProfile = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ('../output/windows_startup_smoke/' + $releaseStamp)))
$releaseConfig = Join-Path $releaseProfile 'Saved/Config/Windows'
New-Item -ItemType Directory -Path $releaseConfig -Force | Out-Null
"[/Script/Engine.GameUserSettings]`nVersion=5`nFrameRateLimit=30.0`n" | Set-Content -LiteralPath (Join-Path $releaseConfig 'GameUserSettings.ini') -Encoding Ascii
$releaseResult = [ordered]@{success=$false;scope='Packaged Windows startup/offscreen image proof only, not real-time gameplay or performance';archive=$releaseArchive;profile=$releaseProfile;resolution=@(1920,1080);rhi='D3D11';test_frame_cap=30;keyboard_tested=$false;full_story_routes_tested=$false;headset_tested=$false;trailer_gameplay_take=$false;supervisor_stop=$true}
$releaseBoot = $null
$releaseGame = $null
try {
    $releaseArgs = '-d3d11 -windowed -ResX=1920 -ResY=1080 -ForceRes -RenderOffScreen -DUMPMOVIE -unattended -NoSound -nosplash -UserDir="' + $releaseProfile.Replace('\','/') + '"'
    $releaseBoot = Start-Process -FilePath $releaseBootstrap -WorkingDirectory $releaseArchive -ArgumentList $releaseArgs -WindowStyle Hidden -PassThru
    $releaseDeadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 150
        $releaseChild = Get-CimInstance Win32_Process -Filter ('ParentProcessId = ' + $releaseBoot.Id) | Where-Object { $_.ExecutablePath -eq $releaseRuntime } | Select-Object -First 1
    } while (-not $releaseChild -and [DateTime]::UtcNow -lt $releaseDeadline)
    if (-not $releaseChild) { throw 'Bootstrap did not launch the expected packaged Shipping executable.' }
    $releaseGame = Get-Process -Id $releaseChild.ProcessId
    $releaseResult.pid = $releaseGame.Id
    $releaseDeadline = [DateTime]::UtcNow.AddSeconds(45)
    $releaseMinimum = [DateTime]::UtcNow.AddSeconds(8)
    do {
        Start-Sleep -Milliseconds 500
        $releaseGame.Refresh()
        $releaseFrames = @(Get-ChildItem -LiteralPath $releaseProfile -Recurse -Filter 'MovieFrame*.png' -ErrorAction SilentlyContinue | Where-Object { $_.Length -gt 15000 })
    } while (-not $releaseGame.HasExited -and ($releaseFrames.Count -lt 20 -or [DateTime]::UtcNow -lt $releaseMinimum) -and [DateTime]::UtcNow -lt $releaseDeadline)
    $releaseResult.frames = @($releaseFrames | Sort-Object Name | Select-Object -First 30 -ExpandProperty FullName)
    $releaseResult.frame_count = $releaseFrames.Count
    $releaseResult.exited_before_supervisor = $releaseGame.HasExited
    $releaseResult.success = $releaseFrames.Count -ge 20 -and -not $releaseGame.HasExited
} catch { $releaseResult.error = $_.Exception.Message }
finally {
    foreach ($releaseOwned in @(@($releaseGame,$releaseRuntime),@($releaseBoot,$releaseBootstrap))) {
        if ($releaseOwned[0]) {
            $releaseObserved = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $releaseOwned[0].Id)
            if ($releaseObserved -and $releaseObserved.ExecutablePath -eq $releaseOwned[1]) { Stop-Process -Id $releaseOwned[0].Id -Force -ErrorAction SilentlyContinue }
        }
    }
    $releaseReport = Join-Path $PSScriptRoot 'release_windows_startup_validation.json'
    $releaseResult | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $releaseReport -Encoding UTF8
    Write-Output ('Packaged startup success=' + $releaseResult.success + '; report=' + $releaseReport)
}
if (-not $releaseResult.success) { exit 1 }
