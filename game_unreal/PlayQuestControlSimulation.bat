@echo off
setlocal
set "QUEST_EDITOR=C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
if not exist "%QUEST_EDITOR%" (
  echo Unreal Engine 5.8 is missing.
  pause
  exit /b 1
)
echo Desktop simulation of the XR character. This does not validate a headset.
"%QUEST_EDITOR%" "%~dp0YesterdayHarbor.uproject" /Game/Quest/Maps/Verdant_VR -game -nohmd -d3d11 -windowed -ResX=1600 -ResY=900
