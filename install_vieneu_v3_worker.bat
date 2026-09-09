@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo Installing independent VieNeu v3 Turbo 3.6.4 CPU/ONNX worker...
cd engines\vieneu_v3_worker
uv sync --inexact
if errorlevel 1 goto fail

set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
    echo VieNeu v3 worker Python not found: %PY%
    goto fail
)

"%PY%" synthesize.py --describe
if errorlevel 1 goto fail

echo.
echo VieNeu v3 CPU/ONNX worker installed successfully.
if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
exit /b 0

:fail
echo.
echo VieNeu v3 worker installation failed. Read the error above, then retry from Model Management.
if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
exit /b 1
