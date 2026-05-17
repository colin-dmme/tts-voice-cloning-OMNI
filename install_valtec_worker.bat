@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo Installing isolated Valtec Vietnamese TTS worker...
cd engines\valtec_worker
uv sync --inexact
if not exist vendor mkdir vendor
if not exist vendor\valtec-tts\.git (
  git clone https://github.com/tronghieuit/valtec-tts.git vendor\valtec-tts
) else (
    git -C vendor\valtec-tts pull --ff-only
)
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
    echo Valtec worker Python not found: %PY%
    exit /b 1
)
uv pip install --python "%PY%" -e vendor\valtec-tts
uv pip install --python "%PY%" torch --index-url https://download.pytorch.org/whl/cpu

if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
