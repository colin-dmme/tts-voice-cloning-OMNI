@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo Starting Colin TTS Studio (PySide6)...
uv sync --inexact --extra qt
REM Launch via module so it works even if the console script wasn't regenerated.
uv run --no-sync python -m omni_tts_ui_qt

pause
