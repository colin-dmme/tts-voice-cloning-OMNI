@echo off
setlocal
cd /d "%~dp0"
echo Installing isolated Supertonic 3 worker...
cd engines\supertonic_worker
uv sync --inexact
if errorlevel 1 exit /b 1
echo Supertonic 3 worker installed.
if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
