@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo Installing isolated Qwen3-TTS worker...
cd engines\qwen_worker
uv sync --inexact
uv pip install qwen-tts
uv pip install torch --index-url https://download.pytorch.org/whl/cu126

pause
