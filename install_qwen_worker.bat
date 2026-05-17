@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo Installing isolated Qwen3-TTS worker...
cd engines\qwen_worker
uv sync --inexact
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
    echo Qwen worker Python not found: %PY%
    exit /b 1
)
uv pip install --python "%PY%" qwen-tts
uv pip install --python "%PY%" torch --index-url https://download.pytorch.org/whl/cu126

if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
