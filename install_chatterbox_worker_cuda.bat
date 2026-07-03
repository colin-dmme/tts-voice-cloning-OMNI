@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo Installing isolated Chatterbox Turbo worker with CUDA PyTorch...
cd engines\chatterbox_worker
uv sync --inexact --upgrade-package chatterbox-tts
if errorlevel 1 goto fail
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
    echo Chatterbox worker Python not found: %PY%
    goto fail
)
uv pip install --python "%PY%" --upgrade chatterbox-tts
if errorlevel 1 goto fail
uv pip install --python "%PY%" "setuptools>=70.0.0,<81.0.0"
if errorlevel 1 goto fail
uv pip install --python "%PY%" --reinstall torch==2.6.0+cu124 torchaudio==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 goto fail

echo.
echo Chatterbox Turbo CUDA worker install completed.
echo You can verify with:
echo engines\chatterbox_worker\.venv\Scripts\python.exe -c "import chatterbox, torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
pause
exit /b 0

:fail
echo.
echo Chatterbox Turbo CUDA worker install failed. Please keep this window open and read the error above.
pause
exit /b 1
