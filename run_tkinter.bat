@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo Starting Colin TTS Local v0.1.0 Tkinter...
uv sync --inexact
uv run --no-sync omni-tts-tkinter

pause
