@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo Installing isolated F5-TTS worker...
cd engines\f5_worker
uv sync --inexact
if errorlevel 1 goto fail
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
    echo F5-TTS worker Python not found: %PY%
    goto fail
)
uv pip install --python "%PY%" f5-tts
if errorlevel 1 goto fail

echo.
echo F5-TTS worker install completed.
pause
exit /b 0

:fail
echo.
echo F5-TTS worker install failed. Please keep this window open and read the error above.
pause
exit /b 1
