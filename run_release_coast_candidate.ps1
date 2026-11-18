param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Export','Prepare','Capture','Validate','Adopt','Revert')]
    [string]$Action,
    [string]$BlenderExe = '',
    [string]$UnrealExe = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
)

$ErrorActionPreference = 'Stop'
$coastRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
if ((Split-Path -Leaf $coastRoot) -ne 'Release_20261026') {
    throw 'This queue launcher is restricted to the Release copy'
}
$activeWriters = @(Get-Process -Name 'UnrealEditor','UnrealEditor-Cmd','blender' -ErrorAction SilentlyContinue)
if ($activeWriters.Count -gt 0) {
    throw ('Root must finish the existing native queue first: ' + (($activeWriters | ForEach-Object { $_.ProcessName + ':' + $_.Id }) -join ', '))
}
$coastProject = Join-Path $coastRoot 'game_unreal\YesterdayHarbor.uproject'
if (-not (Test-Path -LiteralPath $coastProject -PathType Leaf)) { throw 'Release project not found' }
$coastStamp = Get-Date -Format 'yyyyMMddTHHmmssfff'
$coastLogs = Join-Path $coastRoot ('game_unreal\validation\release_coast_queue\' + $coastStamp)
New-Item -ItemType Directory -Path $coastLogs | Out-Null
$coastStdout = Join-Path $coastLogs ($Action + '.stdout.log')
$coastStderr = Join-Path $coastLogs ($Action + '.stderr.log')

if ($Action -eq 'Export') {
    if (-not $BlenderExe -or -not (Test-Path -LiteralPath $BlenderExe -PathType Leaf)) {
        throw 'Supply the existing installed Blender executable with -BlenderExe'
    }
    $coastScript = (Join-Path $coastRoot 'build_release_coast_extension.py').Replace('\','/')
    $coastArgs = @('--background','--factory-startup','--python',('"' + $coastScript + '"'))
    $coastProcess = Start-Process -FilePath $BlenderExe -ArgumentList $coastArgs -WorkingDirectory $coastRoot `
        -WindowStyle Hidden -RedirectStandardOutput $coastStdout -RedirectStandardError $coastStderr -PassThru
} else {
    if (-not (Test-Path -LiteralPath $UnrealExe -PathType Leaf)) { throw 'Existing Unreal executable not found' }
    $coastScriptName = if ($Action -eq 'Capture') { 'capture_release_coast_candidate.py' } else { 'release_coast_candidate.py' }
    $coastScript = (Join-Path $coastRoot ('game_unreal\Python\' + $coastScriptName)).Replace('\','/')
    $coastNativeLog = (Join-Path $coastLogs ($Action + '.native.log')).Replace('\','/')
    $coastUserDir = Join-Path $env:LOCALAPPDATA ('TOSOYQA\Coast_' + $coastStamp)
    if (Test-Path -LiteralPath $coastUserDir) { throw 'Refusing an occupied coast UserDir' }
    New-Item -ItemType Directory -Path $coastUserDir | Out-Null
    $coastArgs = @(('"' + $coastProject.Replace('\','/') + '"'),'-d3d11','-unattended','-nosplash','-NoSound',
        '-RenderOffscreen','-windowed','-ResX=1600','-ResY=900',('-abslog="' + $coastNativeLog + '"'),
        ('-UserDir="' + $coastUserDir.Replace('\','/') + '/"'),
        ('-ExecutePythonScript="' + $coastScript + '"'))
    if ($Action -ne 'Validate') { $coastArgs += '-ReleaseCoastWrite' }
    if ($Action -ne 'Capture') { $coastArgs += ('-ReleaseCoast' + $Action) }
    $coastProcess = Start-Process -FilePath $UnrealExe -ArgumentList $coastArgs -WorkingDirectory $coastRoot `
        -WindowStyle Hidden -RedirectStandardOutput $coastStdout -RedirectStandardError $coastStderr -PassThru
}
[pscustomobject]@{ Action=$Action; ProcessId=$coastProcess.Id; NativeExecuted=$true; LogDirectory=$coastLogs;
    UserDir=$coastUserDir;
    Scope='Release Desktop coast only; inspect reports and root queue completion before next stage' } | ConvertTo-Json
