@echo off
setlocal
cd /d "%~dp0"
echo Installing isolated ZeroTTS GGUF worker...
cd engines\zerotts_gguf_worker
uv sync --inexact
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe build_native.py
if errorlevel 1 exit /b 1
echo ZeroTTS GGUF worker installed.
if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
