@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub

echo Installing optional TTS dependencies for NVIDIA CUDA 12.6...
uv sync --extra tts --inexact
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
    echo App Python not found: %PY%
    exit /b 1
)
uv pip install --python "%PY%" --upgrade --force-reinstall torch==2.7.1+cu126 torchaudio==2.7.1+cu126 --index-url https://download.pytorch.org/whl/cu126

if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
