@echo off
setlocal
cd /d "%~dp0"
echo Installing isolated Kokoro ONNX worker...
cd engines\kokoro_worker
uv sync --inexact
if errorlevel 1 exit /b 1
echo Kokoro ONNX worker installed.
if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
