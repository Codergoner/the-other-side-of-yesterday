# Quest 3 device helpers for the Release copy (dot-source). Windows PowerShell 5.1.
# Every function records what it did; nothing here claims a result it did not observe.
$ErrorActionPreference = 'Stop'
$Quest3Adb = 'C:\Users\USER\TOSOYQuestToolchain\sdk\platform-tools\adb.exe'
$Quest3Package = 'com.yesterdayharbor.quest3'
$Quest3Activity = 'com.epicgames.unreal.GameActivity'
$Quest3SaveRelative = 'files/UnrealGame/YesterdayHarbor/YesterdayHarbor/Saved/SaveGames'
# Android key codes (adb shell input keyevent). The story manager polls these as keyboard keys.
$Quest3Keys = @{ Enter = 66; Up = 19; Down = 20; Left = 21; Right = 22; Escape = 111; Space = 62; Tab = 61;
    E = 33; F = 34; Q = 45; R = 46; T = 48; One = 8; Two = 9; Three = 10; F10 = 140; PageUp = 92; PageDown = 93 }

function Quest3-Adb {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & $Quest3Adb @Arguments 2>&1 | ForEach-Object { "$_" }
    return [pscustomobject]@{ exit = $LASTEXITCODE; text = ($output -join "`n"); lines = @($output) }
}

function Quest3-Device {
    $devices = Quest3-Adb devices -l
    $rows = @($devices.lines | Where-Object { $_ -match '^\S+\s+(device|unauthorized|offline)' })
    if ($rows.Count -lt 1) { return $null }
    $parts = $rows[0] -split '\s+'
    return [pscustomobject]@{ serial = $parts[0]; state = $parts[1]; line = $rows[0] }
}

function Quest3-RequireDevice {
    $device = Quest3-Device
    if (-not $device) { throw 'No Quest 3 is connected (adb devices lists nothing). Connect it by USB-C, enable Developer Mode, accept the USB debugging prompt.' }
    if ($device.state -ne 'device') { throw ('Headset is ' + $device.state + ': accept the USB debugging prompt in the headset (Always allow) and retry.') }
    return $device
}

function Quest3-Props {
    $props = (Quest3-Adb shell getprop).lines
    $wanted = @('ro.product.model', 'ro.product.name', 'ro.product.device', 'ro.build.version.release', 'ro.build.version.sdk', 'ro.build.version.incremental',
        'ro.build.display.id', 'ro.build.fingerprint', 'ro.vros.build.version', 'ro.build.branch', 'ro.hardware', 'ro.soc.model', 'ro.board.platform')
    $result = [ordered]@{}
    foreach ($line in $props) {
        if ($line -match '^\[([^\]]+)\]: \[(.*)\]$' -and $wanted -contains $Matches[1]) { $result[$Matches[1]] = $Matches[2] }
    }
    $result['wm_size'] = (Quest3-Adb shell wm size).text.Trim()
    $result['battery'] = ((Quest3-Adb shell dumpsys battery).lines | Where-Object { $_ -match 'level|temperature' } | ForEach-Object { $_.Trim() }) -join '; '
    return $result
}

function Quest3-Installed { return ((Quest3-Adb shell pm path $Quest3Package).text -match 'package:') }

function Quest3-PackageVersion {
    $dump = (Quest3-Adb shell dumpsys package $Quest3Package).lines
    $version = ($dump | Where-Object { $_ -match 'versionName=' } | Select-Object -First 1)
    $code = ($dump | Where-Object { $_ -match 'versionCode=' } | Select-Object -First 1)
    return [ordered]@{ versionName = if ($version) { $version.Trim() } else { $null }; versionCode = if ($code) { $code.Trim() } else { $null } }
}

function Quest3-Screenshot([string]$Folder, [string]$Name) {
    New-Item -ItemType Directory -Force -Path $Folder | Out-Null
    $remote = '/sdcard/q3_' + $Name + '.png'
    $capture = Quest3-Adb shell screencap -p $remote
    $local = Join-Path $Folder ($Name + '.png')
    $pull = Quest3-Adb pull $remote $local
    Quest3-Adb shell rm $remote | Out-Null
    $ok = (Test-Path -LiteralPath $local) -and ((Get-Item -LiteralPath $local).Length -gt 1000)
    return [ordered]@{ name = $Name; file = $local; ok = $ok; bytes = $(if (Test-Path -LiteralPath $local) { (Get-Item -LiteralPath $local).Length } else { 0 }); utc = [DateTime]::UtcNow.ToString('o') }
}

function Quest3-Key([string]$Key) {
    $code = $Quest3Keys[$Key]
    if ($null -eq $code) { throw ('Unknown key ' + $Key) }
    $result = Quest3-Adb shell input keyevent $code
    return [ordered]@{ key = $Key; code = $code; exit = $result.exit; utc = [DateTime]::UtcNow.ToString('o') }
}

function Quest3-Pid { return (Quest3-Adb shell pidof $Quest3Package).text.Trim() }

function Quest3-SaveDirectory {
    # Debuggable (non-distribution) packages expose their private files through run-as.
    $internal = Quest3-Adb shell run-as $Quest3Package ls -la $Quest3SaveRelative
    if ($internal.exit -eq 0 -and $internal.text -notmatch 'No such file|not debuggable|Permission denied') { return [ordered]@{ kind = 'internal (run-as)'; path = $Quest3SaveRelative; listing = $internal.lines } }
    $external = Quest3-Adb shell ls -la ('/sdcard/Android/data/' + $Quest3Package + '/' + $Quest3SaveRelative)
    return [ordered]@{ kind = 'external files dir'; path = ('/sdcard/Android/data/' + $Quest3Package + '/' + $Quest3SaveRelative); listing = $external.lines; internal_attempt = $internal.text }
}

function Quest3-PullSave([string]$RemoteName, [string]$LocalFile) {
    # run-as cat through exec-out keeps the bytes intact (no shell text conversion).
    $bytes = & $Quest3Adb exec-out run-as $Quest3Package cat ($Quest3SaveRelative + '/' + $RemoteName)
    [IO.File]::WriteAllBytes($LocalFile, [byte[]]$bytes)
    return (Get-Item -LiteralPath $LocalFile).Length
}

function Quest3-StartLogcat([string]$File) {
    Quest3-Adb logcat -c | Out-Null
    return Start-Process -FilePath $Quest3Adb -ArgumentList @('logcat', '-v', 'threadtime') -RedirectStandardOutput $File -WindowStyle Hidden -PassThru
}

function Quest3-Launch {
    $result = Quest3-Adb shell am start -S -W -n ($Quest3Package + '/' + $Quest3Activity)
    return [ordered]@{ utc = [DateTime]::UtcNow.ToString('o'); exit = $result.exit; text = $result.text }
}

function Quest3-ProximityOverride([bool]$Enable) {
    # Meta's documented automation switch: the runtime treats the headset as worn so the app keeps running
    # while nobody wears it. It is undone at the end of every automated session.
    $action = if ($Enable) { 'com.oculus.vrpowermanager.prox_close' } else { 'com.oculus.vrpowermanager.automation_disable' }
    return (Quest3-Adb shell am broadcast -a $action).text
}

function Quest3-Console([string]$Command) {
    # Non-distribution packages register the engine's console-command broadcast receiver.
    return (Quest3-Adb shell am broadcast -a android.intent.action.RUN -e cmd ('"' + $Command + '"')).text
}

function Quest3-WaitLog([string]$File, [string]$Pattern, [int]$TimeoutSeconds) {
    $start = Get-Date
    while (((Get-Date) - $start).TotalSeconds -lt $TimeoutSeconds) {
        if (Test-Path -LiteralPath $File) {
            $hit = Select-String -LiteralPath $File -Pattern $Pattern -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit) { return [ordered]@{ found = $true; line = $hit.Line; seconds = [math]::Round(((Get-Date) - $start).TotalSeconds, 1) } }
        }
        Start-Sleep -Milliseconds 500
    }
    return [ordered]@{ found = $false; seconds = $TimeoutSeconds }
}
