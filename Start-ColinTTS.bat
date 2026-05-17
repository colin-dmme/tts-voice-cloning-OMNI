@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_colin_tts.ps1" %*

if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
