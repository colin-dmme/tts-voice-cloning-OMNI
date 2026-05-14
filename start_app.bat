@echo off
setlocal
cd /d "%~dp0"
set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
start "" "%CD%\.venv\Scripts\pythonw.exe" -m omni_tts_ui_tkinter.main
