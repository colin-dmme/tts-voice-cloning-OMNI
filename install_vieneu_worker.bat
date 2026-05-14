@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo Installing isolated VieNeu-TTS worker...
cd engines\vieneu_worker
uv sync --inexact
uv pip install vieneu --extra-index-url https://pnnbao97.github.io/llama-cpp-python-v0.3.16/cpu/
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
uv pip install torchaudio --index-url https://download.pytorch.org/whl/cpu
uv pip install neucodec

pause
