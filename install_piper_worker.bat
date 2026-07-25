@echo off
setlocal
cd /d "%~dp0"
echo Installing isolated Piper worker...
cd engines\piper_worker
uv sync --inexact
if errorlevel 1 exit /b 1
echo Piper worker installed.
if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
