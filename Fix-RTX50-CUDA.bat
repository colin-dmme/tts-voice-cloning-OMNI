@echo off
setlocal
cd /d "%~dp0"

set PYTORCH_INDEX=https://download.pytorch.org/whl/cu128
set PORTABLE_PY=runtime\python\python.exe
set SOURCE_PY=.venv\Scripts\python.exe
set QWEN_SITE=engines\qwen_worker\site-packages
set QWEN_VENV_PY=engines\qwen_worker\.venv\Scripts\python.exe

echo Fixing PyTorch CUDA for RTX 50xx / Blackwell GPUs...
echo This installs a PyTorch CUDA 12.8 build with sm_120 support.
echo.

if exist "%PORTABLE_PY%" (
    echo Detected portable package.
    call :ensure_pip "%PORTABLE_PY%"
    echo [1/3] Updating portable runtime PyTorch...
    "%PORTABLE_PY%" -m pip install --upgrade --force-reinstall torch torchaudio --index-url %PYTORCH_INDEX%
    if errorlevel 1 exit /b 1

    if exist "%QWEN_SITE%" (
        echo [2/3] Updating portable Qwen worker PyTorch...
        if exist "%QWEN_SITE%\torch" rmdir /s /q "%QWEN_SITE%\torch"
        if exist "%QWEN_SITE%\torchgen" rmdir /s /q "%QWEN_SITE%\torchgen"
        if exist "%QWEN_SITE%\torchaudio" rmdir /s /q "%QWEN_SITE%\torchaudio"
        for /d %%D in ("%QWEN_SITE%\torch-*.dist-info" "%QWEN_SITE%\torchaudio-*.dist-info" "%QWEN_SITE%\nvidia*") do rmdir /s /q "%%~fD" 2>nul
        "%PORTABLE_PY%" -m pip install --upgrade --force-reinstall --target "%QWEN_SITE%" torch --index-url %PYTORCH_INDEX%
        if errorlevel 1 exit /b 1
    ) else (
        echo [2/3] Qwen worker site-packages not found; skipping portable worker patch.
    )

    echo [3/3] Probing portable CUDA...
    "%PORTABLE_PY%" -c "import torch; print('torch:', torch.__version__); print('cuda:', torch.cuda.is_available()); print('device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'); print('arch:', torch.cuda.get_arch_list() if torch.cuda.is_available() else []); assert (not torch.cuda.is_available()) or ('sm_120' in torch.cuda.get_arch_list()), 'PyTorch build does not include sm_120'"
    if errorlevel 1 exit /b 1
    goto done
)

if exist "%SOURCE_PY%" (
    echo Detected source checkout.
    echo [1/3] Updating main project PyTorch...
    uv pip install --python "%SOURCE_PY%" --upgrade --force-reinstall torch torchaudio --index-url %PYTORCH_INDEX%
    if errorlevel 1 exit /b 1

    if exist "%QWEN_VENV_PY%" (
        echo [2/3] Updating Qwen worker PyTorch...
        uv pip install --python "%QWEN_VENV_PY%" qwen-tts
        uv pip install --python "%QWEN_VENV_PY%" --upgrade --force-reinstall torch --index-url %PYTORCH_INDEX%
        if errorlevel 1 exit /b 1
    ) else (
        echo [2/3] Qwen worker venv not found; run install_qwen_worker_blackwell.bat after this if needed.
    )

    echo [3/3] Probing source CUDA...
    "%SOURCE_PY%" -c "import torch; print('torch:', torch.__version__); print('cuda:', torch.cuda.is_available()); print('device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'); print('arch:', torch.cuda.get_arch_list() if torch.cuda.is_available() else []); assert (not torch.cuda.is_available()) or ('sm_120' in torch.cuda.get_arch_list()), 'PyTorch build does not include sm_120'"
    if errorlevel 1 exit /b 1
    goto done
)

echo Could not find portable runtime\python\python.exe or source .venv\Scripts\python.exe.
exit /b 1

:ensure_pip
"%~1" -m pip --version >nul 2>nul
if errorlevel 1 (
    "%~1" -m ensurepip --upgrade
)
exit /b 0

:done
echo.
echo RTX 50xx CUDA fix finished. Restart Colin TTS Local before generating again.
if "%OMNI_TTS_KEEP_WINDOW%"=="1" pause
