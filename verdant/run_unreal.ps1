param(
    [Parameter(Mandatory=$true)][string]$Script,
    [string[]]$Flags = @(),
    [int]$TimeoutSeconds = 900,
    [switch]$NoRender,
    [string]$UserDir = ''
)
# Runs one Verdant editor job and waits for it. One Unreal/Blender writer at a time (AGENTS.md).
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if ((Split-Path -Leaf $root) -ne 'Release_20261026') { throw 'Verdant jobs run only in the Release copy' }
$busy = @(Get-Process -Name 'UnrealEditor','UnrealEditor-Cmd','blender' -ErrorAction SilentlyContinue)
if ($busy.Count -gt 0) { throw ('Another native writer is running: ' + (($busy | ForEach-Object { $_.ProcessName + ':' + $_.Id }) -join ', ')) }
$project = (Join-Path $root 'game_unreal\YesterdayHarbor.uproject').Replace('\','/')
$python = (Join-Path $root ('game_unreal\Python\' + $Script)).Replace('\','/')
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Missing job $python" }
$stamp = Get-Date -Format 'yyyyMMddTHHmmss'
$logs = Join-Path $root 'game_unreal\validation\verdant\runs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$log = (Join-Path $logs ($stamp + '_' + [IO.Path]::GetFileNameWithoutExtension($Script) + '.log')).Replace('\','/')
$user = if ($UserDir) { $UserDir } else { Join-Path $env:LOCALAPPDATA 'TOSOYQA\Verdant' }
New-Item -ItemType Directory -Force -Path $user | Out-Null
$arguments = @(('"' + $project + '"'), '-d3d11', '-unattended', '-nosplash', '-NoSound', '-windowed', '-ResX=1600', '-ResY=900',
    ('-abslog="' + $log + '"'), ('-UserDir="' + $user.Replace('\','/') + '/"'), ('-ExecutePythonScript="' + $python + '"'))
if ($NoRender) { $arguments += '-nullrhi' } else { $arguments += '-RenderOffscreen' }
$arguments += $Flags
$editor = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$process = Start-Process -FilePath $editor -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru
$started = Get-Date
if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    Stop-Process -Id $process.Id -Force
    throw "Timed out after $TimeoutSeconds s; log $log"
}
[pscustomobject]@{ seconds = [int]((Get-Date) - $started).TotalSeconds; exit = $process.ExitCode; log = $log } | ConvertTo-Json
if (Test-Path -LiteralPath $log) {
    Select-String -LiteralPath $log -Pattern 'LogPython: .*VERDANT |LogPython: Error|LogEditorPythonExecuter: Error' |
        Select-Object -Last 40 | ForEach-Object { $_.Line }
}
