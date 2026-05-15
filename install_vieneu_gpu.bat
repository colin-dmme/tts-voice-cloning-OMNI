@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo ============================================
echo  Installing VieNeu-TTS worker with GPU support
echo  (torch CUDA 12.8 + lmdeploy + triton)
echo ============================================
echo.

cd engines\vieneu_worker

echo [1/6] Syncing base dependencies...
uv sync --inexact

echo [2/6] Installing vieneu SDK...
uv pip install vieneu --extra-index-url https://pnnbao97.github.io/llama-cpp-python-v0.3.16/cpu/

echo [3/6] Installing lmdeploy (GPU backend)...
uv pip install https://github.com/InternLM/lmdeploy/releases/download/v0.11.0/lmdeploy-0.11.0+cu128-cp312-cp312-win_amd64.whl

echo [4/6] Installing torch + torchaudio (CUDA 12.8) - MUST be after lmdeploy...
uv pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128

echo [5/6] Installing neucodec + triton-windows...
uv pip install neucodec triton-windows

echo [6/6] Pinning pyarrow to stable version...
uv pip install "pyarrow>=19.0,<20.0"

echo.
echo ============================================
echo  Done! GPU worker is ready.
echo  Verify: .venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"
echo ============================================

pause
