@echo off
setlocal
cd /d "%~dp0"
echo Installing isolated ZeroTTS 0.1.2 worker...
cd engines\zerotts_worker
uv sync --inexact
if errorlevel 1 exit /b 1
echo ZeroTTS worker installed.
if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
