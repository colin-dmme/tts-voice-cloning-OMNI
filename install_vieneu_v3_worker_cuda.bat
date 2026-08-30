@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

call install_vieneu_v3_worker.bat
if errorlevel 1 goto fail

cd /d "%~dp0engines\vieneu_v3_worker"
set PY=.venv\Scripts\python.exe
if not exist "%PY%" goto fail

set TORCH_INDEX=https://download.pytorch.org/whl/cu118
set TORCH_VERSION=2.7.1
for /f "delims=" %%G in ('nvidia-smi --query-gpu^=name --format^=csv^,noheader 2^>nul') do set GPU_NAME=%%G
echo Detected GPU: %GPU_NAME%
echo %GPU_NAME% | findstr /i "RTX 50 5090 5080 5070 5060" >nul
if not errorlevel 1 (
    set TORCH_INDEX=https://download.pytorch.org/whl/cu128
    set TORCH_VERSION=2.8.0
)

echo Installing PyTorch CUDA %TORCH_VERSION% for VieNeu v3...
uv pip install --python "%PY%" --reinstall torch==%TORCH_VERSION% torchaudio==%TORCH_VERSION% --index-url %TORCH_INDEX%
if errorlevel 1 goto fail
uv pip install --python "%PY%" "transformers==4.57.6"
if errorlevel 1 goto fail

"%PY%" synthesize.py --describe
if errorlevel 1 goto fail

echo.
echo VieNeu v3 GPU/PyTorch worker installed successfully.
if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
exit /b 0

:fail
echo.
echo VieNeu v3 GPU installation failed. CPU ONNX remains available if its installation completed.
if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
exit /b 1
