param(
    [string]$Script = 'trailer_director.py',
    [string[]]$Flags = @('-Quest3TrailerTake'),
    [int]$TimeoutSeconds = 1500,
    [int]$Width = 1600,
    [int]$Height = 900,
    [string]$Label = 'director'
)
# Runs a trailer take: the visible Unreal editor plays the game in its level viewport (the Quest pawn, desktop
# preview camera) under game_unreal/Python/<Script>, and the editor window is recorded with Windows Graphics Capture.
# The floating-window play setting below is not honoured by this engine build, so before play starts the editor
# window must be maximized and the viewport put in immersive mode (F11) by hand; then create
# game_unreal/validation/trailer/go.txt. The recorder starts on that file (the capture keeps its starting size).
# The 20261111T141922 take ended early after the jump fade (a null actor in the post-jump dolly); the footage up to
# there is complete. Crop the editor chrome in the edit (see output/trailer_edit/edit.json, source "pie").
# Footage label: Unreal editor preview of the Quest build on PC with simulated hand input. Not a headset, not the APK.
# One Unreal process at a time. Output: output/trailer_takes/<stamp>_<label>/take.mkv plus take.json.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if ((Split-Path -Leaf $root) -ne 'Release_20261026') { throw 'Trailer takes run only in the Release copy' }
$busy = @(Get-Process -Name 'UnrealEditor','UnrealEditor-Cmd','blender' -ErrorAction SilentlyContinue)
if ($busy.Count -gt 0) { throw ('Another native writer is running: ' + (($busy | ForEach-Object { $_.ProcessName + ':' + $_.Id }) -join ', ')) }
$ffmpeg = Join-Path $root 'output\capture_tools\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe'
$editor = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$project = (Join-Path $root 'game_unreal\YesterdayHarbor.uproject').Replace('\','/')
$python = (Join-Path $root ('game_unreal\Python\' + $Script)).Replace('\','/')
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Missing $python" }
$stamp = Get-Date -Format 'yyyyMMddTHHmmss'
$folder = Join-Path $root ("output\trailer_takes\{0}_{1}" -f $stamp, $Label)
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$user = "C:\Users\USER\TOSOYReleaseQA\TRL_$stamp"
$config = Join-Path $user 'Saved\Config\WindowsEditor'
New-Item -ItemType Directory -Force -Path $config | Out-Null
# Play in a floating window of a fixed size so the take is the game picture only (no editor panels).
@"
[/Script/UnrealEd.LevelEditorPlaySettings]
LastExecutedPlayModeType=PlayMode_InEditorFloating
LastExecutedPlayModeLocation=PlayLocation_DefaultPlayerStart
NewWindowWidth=$Width
NewWindowHeight=$Height
CenterNewWindow=True
ShowMouseControlLabel=False
"@ | Set-Content -LiteralPath (Join-Path $config 'EditorPerProjectUserSettings.ini') -Encoding ascii
$log = (Join-Path $folder 'editor.log').Replace('\','/')
# The director waits for this file before it starts play, so the viewport can be put in immersive mode (F11) first.
$go = Join-Path $root 'game_unreal\validation\trailer\go.txt'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $go) | Out-Null
Remove-Item -LiteralPath $go -ErrorAction SilentlyContinue
$arguments = @(('"' + $project + '"'), '-d3d11', '-unattended', '-nosplash', '-windowed', '-WinX=0', '-WinY=0', '-ResX=1920', '-ResY=1040',
    ('-abslog="' + $log + '"'), ('-UserDir="' + $user.Replace('\','/') + '/"'), ('-ExecutePythonScript="' + $python + '"')) + $Flags
$process = Start-Process -FilePath $editor -ArgumentList $arguments -WorkingDirectory $root -PassThru
$started = Get-Date
$take = Join-Path $folder 'take.mkv'
$graph = "gfxcapture=window_title='(?i)Unreal Editor':capture_cursor=false:capture_border=false:max_framerate=30:output_fmt=bgra,hwdownload,format=bgra,fps=30,format=yuv420p"
$recorder = $null
$recorderStart = $null
# The PIE window appears after the map loads: keep trying until the capture holds for more than a few seconds.
while (-not $process.HasExited -and ((Get-Date) - $started).TotalSeconds -lt $TimeoutSeconds) {
    # Recording starts only once the go file exists (the window has its final size by then: the capture keeps the size it starts with).
    if (-not (Test-Path -LiteralPath $go)) { Start-Sleep -Milliseconds 300; continue }
    if ($null -eq $recorder -or $recorder.HasExited) {
        if ($recorder -and ((Get-Date) - $recorderStart).TotalSeconds -gt 8) { break }  # the window closed after a real take
        $info = New-Object System.Diagnostics.ProcessStartInfo
        $info.FileName = $ffmpeg
        $info.Arguments = "-hide_banner -loglevel error -y -f lavfi -i `"$graph`" -t $TimeoutSeconds -c:v libx264 -preset veryfast -crf 14 -g 30 -pix_fmt yuv420p `"$take`""
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $recorderStart = Get-Date
        $recorder = [System.Diagnostics.Process]::Start($info)
    }
    Start-Sleep -Milliseconds 700
}
if (-not $process.HasExited) {
    if (-not $process.WaitForExit([Math]::Max(1000, ($TimeoutSeconds - [int]((Get-Date) - $started).TotalSeconds) * 1000))) { Stop-Process -Id $process.Id -Force }
}
if ($recorder -and -not $recorder.HasExited) { Stop-Process -Id $recorder.Id -Force }
Start-Sleep -Seconds 1
$report = Get-ChildItem (Join-Path $root 'game_unreal\validation\trailer') -Filter 'director_report_latest.json' -ErrorAction SilentlyContinue | Select-Object -First 1
$summary = [ordered]@{
    stamp = $stamp; script = $Script; editor_exit = $process.ExitCode; seconds = [int]((Get-Date) - $started).TotalSeconds
    take = $take; take_bytes = $(if (Test-Path -LiteralPath $take) { (Get-Item -LiteralPath $take).Length } else { 0 })
    recorder_started_utc = $(if ($recorderStart) { $recorderStart.ToUniversalTime().ToString('o') } else { $null })
    recorder_started_unix = $(if ($recorderStart) { [double]([DateTimeOffset]$recorderStart).ToUnixTimeMilliseconds() / 1000.0 } else { $null })
    director_report = $(if ($report) { $report.FullName } else { $null })
    footage_label = 'Unreal editor preview of the Quest build on PC, simulated hand input; not a headset, not the APK'
}
if ($report) { Copy-Item -LiteralPath $report.FullName -Destination (Join-Path $folder 'director_report.json') -Force }
$summary | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $folder 'take.json') -Encoding utf8
$summary | ConvertTo-Json
