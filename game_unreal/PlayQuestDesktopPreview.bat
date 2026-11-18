@echo off
setlocal
set "QUEST_EDITOR=C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
if not exist "%QUEST_EDITOR%" (
  echo Unreal Engine 5.8 is missing.
  pause
  exit /b 1
)
"%QUEST_EDITOR%" "%~dp0YesterdayHarbor.uproject" /Game/Quest/Maps/Verdant_Desktop -game -nohmd -d3d11 -windowed -ResX=1600 -ResY=900
