@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo Installing isolated F5-TTS worker with CUDA PyTorch...
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
uv pip install --python "%PY%" --reinstall torch==2.7.1+cu126 torchaudio==2.7.1+cu126 --index-url https://download.pytorch.org/whl/cu126
if errorlevel 1 goto fail

echo.
echo F5-TTS CUDA worker install completed.
echo You can verify with:
echo engines\f5_worker\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
pause
exit /b 0

:fail
echo.
echo F5-TTS CUDA worker install failed. Please keep this window open and read the error above.
pause
exit /b 1
