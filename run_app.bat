@echo off
setlocal
cd /d "%~dp0"

REM Do not let a parent launcher force uv to reuse its own virtual environment.
set "VIRTUAL_ENV="
set "UV_PROJECT_ENVIRONMENT="

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo Starting Colin TTS Local v0.1.0...
uv sync --inexact
uv run --no-sync omni-tts-gradio

pause
