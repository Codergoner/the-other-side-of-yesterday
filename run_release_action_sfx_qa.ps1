param(
    [string]$UnrealExe = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
)

$ErrorActionPreference = 'Stop'
$sfxRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
if ((Split-Path -Leaf $sfxRoot) -ne 'Release_20261026') { throw 'SFX QA refuses another project' }
$sfxActive = @(Get-Process -Name 'UnrealEditor','UnrealEditor-Cmd','blender' -ErrorAction SilentlyContinue)
if ($sfxActive.Count -gt 0) { throw 'Root must finish the current native writer/QA queue before this isolated run' }
if (-not (Test-Path -LiteralPath $UnrealExe -PathType Leaf)) { throw 'Existing Unreal editor executable not found' }
$sfxStamp = Get-Date -Format 'yyyyMMddTHHmmssfff'
$sfxUserDir = Join-Path $env:TEMP ('YRSfx_' + $sfxStamp)
if (Test-Path -LiteralPath $sfxUserDir) { throw 'Refusing an occupied QA UserDir' }
New-Item -ItemType Directory -Path $sfxUserDir | Out-Null
$sfxProject = (Join-Path $sfxRoot 'game_unreal\YesterdayHarbor.uproject').Replace('\','/')
$sfxScript = (Join-Path $sfxRoot 'game_unreal\Python\validate_release_action_sfx.py').Replace('\','/')
$sfxLog = (Join-Path $sfxUserDir 'YesterdayHarbor.log').Replace('\','/')
$sfxStdout = Join-Path $sfxUserDir 'stdout.log'
$sfxStderr = Join-Path $sfxUserDir 'stderr.log'
$sfxArgs = @(('"' + $sfxProject + '"'),'-d3d11','-unattended','-nosplash','-RenderOffscreen','-windowed','-ResX=1920','-ResY=1080',
    '-ReleaseStoryQA','-ReleaseStoryAudioQA','-ReleaseActionSfxQA',
    ('-UserDir="' + $sfxUserDir.Replace('\','/') + '/"'),('-abslog="' + $sfxLog + '"'),
    ('-ExecutePythonScript="' + $sfxScript + '"'))
$sfxProcess = Start-Process -FilePath $UnrealExe -ArgumentList $sfxArgs -WorkingDirectory $sfxRoot `
    -WindowStyle Hidden -RedirectStandardOutput $sfxStdout -RedirectStandardError $sfxStderr -PassThru
[pscustomobject]@{ ProcessId=$sfxProcess.Id; UserDir=$sfxUserDir; NativeLog=$sfxLog;
    Report=(Join-Path $sfxRoot 'game_unreal\release_action_sfx_validation.json');
    Scope='Actual native PIE actions and mixer QA; no packaged/physical-input/headset/performance assertion' } | ConvertTo-Json
