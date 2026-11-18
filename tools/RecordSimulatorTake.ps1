param(
    [ValidateSet('Start','Stop','Status')][string]$Mode = 'Start',
    [string]$Label = 'take',
    [int]$MaxSeconds = 1800,
    [int]$Fps = 30,
    [string]$WindowTitle = '(?i)YesterdayHarbor'
)
# Records the game window of a Meta XR Simulator session (tools/RunQuest3Simulator.ps1) for the competition video.
# Windows Graphics Capture of that one window only (no desktop, no cursor, no microphone), H.264 in Matroska so a take
# survives being stopped. Footage label: Meta XR Simulator footage (OpenXR on Windows), not a headset recording.
#   Start : begins a take in output/trailer_takes/<stamp>_<label>/take.mkv and returns at once.
#   Stop  : ends every running take.     Status: lists running takes.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$ffmpeg = Join-Path $root 'output\capture_tools\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe'
if (-not (Test-Path -LiteralPath $ffmpeg)) { throw "ffmpeg not found at $ffmpeg" }
$running = @(Get-CimInstance Win32_Process -Filter "Name='ffmpeg.exe'" | Where-Object { $_.CommandLine -match 'gfxcapture' -and $_.CommandLine -match 'trailer_takes' })
if ($Mode -eq 'Status') { $running | ForEach-Object { "{0}  {1}" -f $_.ProcessId, ($_.CommandLine -replace '.*trailer_takes', 'trailer_takes') }; exit 0 }
if ($Mode -eq 'Stop') {
    foreach ($p in $running) { Stop-Process -Id $p.ProcessId -Force }
    Start-Sleep -Milliseconds 800
    "stopped $($running.Count) take(s)"
    exit 0
}
if ($running.Count -gt 0) { throw 'A take is already running; stop it first.' }
$stamp = Get-Date -Format 'yyyyMMddTHHmmss'
$folder = Join-Path $root ("output\trailer_takes\{0}_{1}" -f $stamp, $Label)
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$out = Join-Path $folder 'take.mkv'
$graph = "gfxcapture=window_title='$WindowTitle':capture_cursor=false:capture_border=false:max_framerate=${Fps}:output_fmt=bgra,hwdownload,format=bgra,fps=$Fps,format=yuv420p"
$info = New-Object System.Diagnostics.ProcessStartInfo
$info.FileName = $ffmpeg
$info.Arguments = "-hide_banner -loglevel warning -y -f lavfi -i `"$graph`" -t $MaxSeconds -c:v libx264 -preset veryfast -crf 15 -g $Fps -pix_fmt yuv420p `"$out`""
$info.UseShellExecute = $false
$info.CreateNoWindow = $true
$info.WorkingDirectory = $folder
$process = [System.Diagnostics.Process]::Start($info)
[ordered]@{ pid = $process.Id; take = $out; label = $Label; fps = $Fps; started = (Get-Date).ToString('o');
            footage_label = 'Meta XR Simulator footage (OpenXR on Windows); game window only' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $folder 'take.json') -Encoding utf8
"recording pid $($process.Id) -> $out"
