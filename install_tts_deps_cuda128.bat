@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub

echo Installing optional TTS dependencies for NVIDIA CUDA 12.8 / RTX 50xx Blackwell...
echo Note: use install_tts_deps_cuda126.bat or install_vieneu_worker_cuda.bat for older Pascal cards such as GTX 1080 Ti.
uv sync --extra tts --inexact
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
    echo App Python not found: %PY%
    exit /b 1
)
uv pip install --python "%PY%" --upgrade --force-reinstall torch torchaudio --index-url https://download.pytorch.org/whl/cu128
"%PY%" -c "import torch; print('torch:', torch.__version__); print('cuda:', torch.cuda.is_available()); print('device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'); print('arch:', torch.cuda.get_arch_list() if torch.cuda.is_available() else [])"

if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
