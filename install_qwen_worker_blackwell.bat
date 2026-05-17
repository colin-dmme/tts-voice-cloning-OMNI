@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo Installing isolated Qwen3-TTS worker for RTX 50xx / Blackwell CUDA 12.8...
cd engines\qwen_worker
uv sync --inexact
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
    echo Qwen worker Python not found: %PY%
    exit /b 1
)
uv pip install --python "%PY%" qwen-tts
uv pip install --python "%PY%" --upgrade --force-reinstall torch --index-url https://download.pytorch.org/whl/cu128
"%PY%" -c "import torch; print('torch:', torch.__version__); print('cuda:', torch.cuda.is_available()); print('device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'); print('arch:', torch.cuda.get_arch_list() if torch.cuda.is_available() else []); assert (not torch.cuda.is_available()) or ('sm_120' in torch.cuda.get_arch_list()), 'PyTorch build does not include sm_120'"

if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
