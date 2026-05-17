@echo off
setlocal
cd /d "%~dp0"

set HF_HOME=%CD%\.hf_cache
set HF_HUB_CACHE=%CD%\.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo Installing VieNeu-TTS worker with CUDA support (GTX 1080 Ti / Pascal+)...
echo Requires: NVIDIA GPU with CUDA 11.x driver (Pascal / Turing / Ampere)
echo.

cd engines\vieneu_worker

:: Base dependencies (no torch yet)
uv sync --inexact
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
    echo VieNeu worker Python not found: %PY%
    exit /b 1
)

:: PyTorch CUDA 11.8 — compatible with Pascal (GTX 1080 Ti) and newer
echo [1/6] Installing PyTorch cu118...
uv pip install --python "%PY%" --force-reinstall torch torchaudio --index-url https://download.pytorch.org/whl/cu118

:: VieNeu package. CUDA acceleration is guaranteed for torch/ONNX modes.
:: GGUF CUDA additionally needs a compatible local llama-cpp-python CUDA wheel.
echo [2/6] Installing VieNeu package...
uv pip install --python "%PY%" --force-reinstall vieneu --extra-index-url https://pnnbao97.github.io/llama-cpp-python-v0.3.16/cpu/
if errorlevel 1 (
    exit /b 1
)

set LLAMA_CUDA_WHEEL=
for %%W in ("..\..\runtime_wheels\windows\cp312\cuda\llama_cpp_python-0.3.16-*.whl") do set "LLAMA_CUDA_WHEEL=%%~fW"
if defined LLAMA_CUDA_WHEEL (
    echo [2b/6] Installing local llama.cpp CUDA wheel...
    uv pip install --python "%PY%" --force-reinstall --no-deps "%LLAMA_CUDA_WHEEL%"
    if errorlevel 1 (
        exit /b 1
    )
) else (
    echo [2b/6] Local llama.cpp CUDA wheel not found; GGUF CUDA will stay unavailable.
)

:: ONNX Runtime GPU (replaces CPU-only onnxruntime for codec acceleration)
echo [3/6] Installing onnxruntime-gpu...
uv pip uninstall --python "%PY%" onnxruntime -y 2>nul
uv pip install --python "%PY%" --force-reinstall onnxruntime-gpu

:: neucodec (voice cloning codec)
echo [4/6] Installing neucodec...
uv pip install --python "%PY%" --force-reinstall neucodec

:: huggingface_hub for LoRA mode snapshot_download
echo [5/6] Installing huggingface_hub...
uv pip install --python "%PY%" huggingface_hub

:: neucodec can pull CPU torch again; force CUDA torch last.
echo [6/6] Re-applying PyTorch cu118 after dependencies...
uv pip install --python "%PY%" --force-reinstall torch==2.7.1+cu118 torchaudio==2.7.1+cu118 --index-url https://download.pytorch.org/whl/cu118

echo.
echo CUDA worker installed. VieNeu Turbo/PyTorch can use CUDA when available.
if defined LLAMA_CUDA_WHEEL (
    echo GGUF CUDA wheel installed from: %LLAMA_CUDA_WHEEL%
) else (
    echo GGUF CUDA requires llama.cpp GPU offload; local wheel was not found.
)
if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
