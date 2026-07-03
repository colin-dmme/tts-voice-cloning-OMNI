@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cls

REM Enable ANSI colors in Windows 10+
for /F "tokens=1,2 delims=#" %%a in ('"prompt #$H#$E# & echo on & for %%b in (1) do rem"') do (
  set "ESC=%%b"
)

set "GREEN=%ESC%[92m"
set "RED=%ESC%[91m"
set "YELLOW=%ESC%[93m"
set "CYAN=%ESC%[96m"
set "RESET=%ESC%[0m"

title Colin TTS Local (Auto-Clone)
echo %CYAN%============================================%RESET%
echo %CYAN%    Colin TTS Local%RESET%
echo %CYAN%    Auto-clone, auto-setup, one-click start%RESET%
echo %CYAN%============================================%RESET%
echo.

set "APP_NAME=Colin TTS Local"
set "REPO_URL=https://github.com/colin-dmme/tts-voice-cloning-OMNI.git"
set "PROJECT_FOLDER=tts-voice-cloning-OMNI"
set "VALIDATION_FILE=pyproject.toml"
set "PYTHON_VERSION=3.12"

cd /d "%~dp0"
set "CONFIG_FILE=%~dp0colin-tts-launcher-path.txt"

if /i "%~1"=="--check" goto SelfCheck
if /i "%~1"=="--web" set "START_MODE=web"
if /i "%~1"=="--desktop" set "START_MODE=desktop"
if /i "%~1"=="--sync-only" set "START_MODE=sync"

echo [1/4] Checking project source...
echo.

if exist "%CONFIG_FILE%" (
    set /p SAVED_PATH=<"%CONFIG_FILE%"
    if exist "!SAVED_PATH!\%VALIDATION_FILE%" (
        echo %GREEN%Found saved project:%RESET% !SAVED_PATH!
        echo.
        choice /C YN /D Y /T 5 /M "Run now without updating? [Y=Run, N=Update]"
        if errorlevel 2 (
            cd /d "!SAVED_PATH!"
            call :MaybePull
            goto SyncDeps
        )
        cd /d "!SAVED_PATH!"
        goto SyncDeps
    ) else (
        echo %YELLOW%Saved path is no longer valid:%RESET% !SAVED_PATH!
        del "%CONFIG_FILE%" >nul 2>&1
        echo.
    )
)

REM Case 1: this launcher is already inside the project folder.
if exist "%VALIDATION_FILE%" (
    echo %GREEN%Found project in current folder.%RESET%
    echo !CD!>"%CONFIG_FILE%"
    echo.
    choice /C YN /D Y /T 5 /M "Run now without updating? [Y=Run, N=Update]"
    if errorlevel 2 call :MaybePull
    goto SyncDeps
)

REM Case 2: project folder exists next to this launcher.
if exist "%PROJECT_FOLDER%\%VALIDATION_FILE%" (
    echo %GREEN%Found project in subfolder:%RESET% %PROJECT_FOLDER%
    echo.
    choice /C YN /D Y /T 5 /M "Run now without updating? [Y=Run, N=Update]"
    set "RUN_CHOICE=%ERRORLEVEL%"
    cd /d "%PROJECT_FOLDER%"
    echo !CD!>"%CONFIG_FILE%"
    if "!RUN_CHOICE!"=="2" call :MaybePull
    goto SyncDeps
)

goto FullSetup

:FullSetup
echo %YELLOW%Project source was not found. Setting up from GitHub.%RESET%
echo.

call :EnsureGit
if errorlevel 1 (
    echo %RED%[ERROR] Git is required to clone this project.%RESET%
    echo Install Git manually, then run this launcher again.
    goto ErrorExit
)
call :ChooseBranch
call :ChooseClonePath

if not exist "!CLONE_PATH!" mkdir "!CLONE_PATH!"
if errorlevel 1 (
    echo %RED%[ERROR] Could not create target folder:%RESET% !CLONE_PATH!
    goto ErrorExit
)

cd /d "!CLONE_PATH!"
if exist "%PROJECT_FOLDER%\%VALIDATION_FILE%" (
    echo %GREEN%Existing valid project found. Using it.%RESET%
    cd /d "%PROJECT_FOLDER%"
    echo !CD!>"%CONFIG_FILE%"
    goto SyncDeps
)

if exist "%PROJECT_FOLDER%" (
    echo %RED%[ERROR] Target folder already exists but is not a valid project:%RESET%
    echo   !CLONE_PATH!\%PROJECT_FOLDER%
    echo.
    echo Please choose a different parent folder or move that folder aside.
    goto ErrorExit
)

echo.
echo Cloning branch %GREEN%!SELECTED_BRANCH!%RESET% from GitHub...
git clone -b !SELECTED_BRANCH! "%REPO_URL%" "%PROJECT_FOLDER%"
if errorlevel 1 (
    call :GitAuthRetry
    if errorlevel 1 goto ErrorExit
)

:AfterSourceReady
if not exist "%PROJECT_FOLDER%\%VALIDATION_FILE%" (
    echo %RED%[ERROR] Source setup finished, but %VALIDATION_FILE% was not found.%RESET%
    goto ErrorExit
)

cd /d "%PROJECT_FOLDER%"
echo !CD!>"%CONFIG_FILE%"
goto SyncDeps

:SyncDeps
echo.
echo [2/4] Checking uv, Python, and FFmpeg...
echo.
call :EnsureUv
call :EnsurePython
call :EnsureFfmpeg

set "HF_HOME=%CD%\.hf_cache"
set "HF_HUB_CACHE=%CD%\.hf_cache\hub"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"

echo.
echo [3/4] Syncing dependencies...
echo.
uv sync --python %PYTHON_VERSION% --inexact
if errorlevel 1 (
    echo %RED%[ERROR] Could not sync dependencies.%RESET%
    goto ErrorExit
)

if exist "scripts\restore_user_state.py" (
    echo.
    echo Restoring saved app state...
    uv run --no-sync python scripts\restore_user_state.py
    if errorlevel 1 (
        echo %YELLOW%[WARNING] State restore failed. The app can still start.%RESET%
    )
)

if /i "%START_MODE%"=="web" goto RunWeb
if /i "%START_MODE%"=="desktop" goto RunDesktop
if /i "%START_MODE%"=="sync" goto NormalExit
goto ActionMenu

:ActionMenu
echo.
echo %CYAN%============================================%RESET%
echo %CYAN%    Choose action%RESET%
echo %CYAN%============================================%RESET%
echo.
echo   [1] Start desktop UI %GREEN%(default)%RESET%
echo   [2] Start web UI
echo   [3] Sync only, then exit
echo   [4] Open project folder
echo   [Q] Exit
echo.
choice /C 1234Q /D 1 /T 5 /M "Choose action"
if errorlevel 5 goto NormalExit
if errorlevel 4 goto OpenFolder
if errorlevel 3 goto NormalExit
if errorlevel 2 goto RunWeb
goto RunDesktop

:RunDesktop
echo.
echo [4/4] Starting desktop UI...
echo.
uv run --no-sync omni-tts-tkinter
if errorlevel 1 (
    echo.
    echo %RED%[ERROR] The desktop app exited with an error.%RESET%
    goto ErrorExit
)
goto RestartPrompt

:RunWeb
echo.
echo [4/4] Starting web UI...
echo.
uv run --no-sync omni-tts-gradio
if errorlevel 1 (
    echo.
    echo %RED%[ERROR] The web app exited with an error.%RESET%
    goto ErrorExit
)
goto RestartPrompt

:OpenFolder
start "" "%CD%"
goto ActionMenu

:RestartPrompt
echo.
echo %GREEN%App closed.%RESET%
echo.
choice /C YN /D N /T 10 /M "Run again? [Y=Yes, N=Exit]"
if errorlevel 2 goto NormalExit
goto ActionMenu

:NormalExit
echo.
echo %GREEN%Done. Closing in 3 seconds...%RESET%
timeout /t 3 2>nul
if errorlevel 1 ping -n 4 127.0.0.1 >nul
exit

:ErrorExit
echo.
echo %RED%Stopped because an error occurred. Please read the message above.%RESET%
pause
exit /b 1

:SelfCheck
echo Configuration preview:
echo   App Name:        %APP_NAME%
echo   Repository:      %REPO_URL%
echo   Project Folder:  %PROJECT_FOLDER%
echo   Bat Filename:    colin-tts-launcher.bat
echo   Dep Manager:     uv
echo   Python:          %PYTHON_VERSION% managed by uv
echo   Git:             Auto-install with winget when needed
echo   FFmpeg:          Auto-install with winget when needed
echo   Private repo:    Git login retry enabled
echo   Main Command:    uv run --no-sync omni-tts-tkinter
echo   Validation File: %VALIDATION_FILE%
echo   Config File:     %CONFIG_FILE%
echo.
echo %GREEN%Self-check completed.%RESET%
exit /b 0

:MaybePull
if not exist ".git" (
    echo %YELLOW%No Git repository found. Skipping source update.%RESET%
    exit /b 0
)
call :EnsureGit
if errorlevel 1 (
    echo %YELLOW%Git is not available. Skipping source update.%RESET%
    exit /b 0
)
echo Updating source...
git pull --ff-only
if errorlevel 1 (
    echo %YELLOW%Source update failed. If this is a private repo, please sign in and retry.%RESET%
    call :GitLogin
    echo Retrying source update...
    git pull --ff-only
    if errorlevel 1 (
        echo %YELLOW%[WARNING] Source update still failed. Continuing with local files.%RESET%
    )
)
exit /b 0

:EnsureGit
set "PATH=%ProgramFiles%\Git\cmd;%ProgramFiles(x86)%\Git\cmd;%LOCALAPPDATA%\Programs\Git\cmd;%PATH%"
git --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%g in ('git --version') do echo %GREEN%%%g%RESET%
    exit /b 0
)

echo %YELLOW%Git was not found. Trying to install Git with winget...%RESET%
winget --version >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%winget is not available, so Git cannot be installed automatically.%RESET%
    exit /b 1
)

winget install --id Git.Git --exact --source winget --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo %YELLOW%Git installation failed or was cancelled.%RESET%
    exit /b 1
)

set "PATH=%ProgramFiles%\Git\cmd;%ProgramFiles(x86)%\Git\cmd;%LOCALAPPDATA%\Programs\Git\cmd;%PATH%"
git --version >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%Git was installed but is not visible in this window yet.%RESET%
    echo Close this window and run the launcher again to use git clone.
    exit /b 1
)

for /f "tokens=*" %%g in ('git --version') do echo %GREEN%%%g%RESET%
exit /b 0

:GitLogin
git credential-manager --version >nul 2>&1
if not errorlevel 1 (
    echo Opening GitHub sign-in via Git Credential Manager...
    git credential-manager github login
    exit /b 0
)

echo %YELLOW%Git Credential Manager was not found.%RESET%
echo If the repo is private, run this once in a terminal, then rerun this launcher:
echo   git clone %REPO_URL%
exit /b 1

:GitAuthRetry
echo.
echo %YELLOW%Git clone failed.%RESET%
echo If this repository is private, sign in to GitHub when the login window opens.
echo.
call :GitLogin
echo.
choice /C YN /D Y /T 60 /M "Retry git clone now? [Y=Retry, N=Stop]"
if errorlevel 2 exit /b 1

if exist "%PROJECT_FOLDER%" (
    if not exist "%PROJECT_FOLDER%\%VALIDATION_FILE%" (
        echo %RED%[ERROR] A partial or invalid folder already exists:%RESET% !CLONE_PATH!\%PROJECT_FOLDER%
        echo Move or delete that folder, then run this launcher again.
        exit /b 1
    )
)

git clone -b !SELECTED_BRANCH! "%REPO_URL%" "%PROJECT_FOLDER%"
if errorlevel 1 (
    echo %RED%[ERROR] Git clone still failed after retry.%RESET%
    exit /b 1
)
exit /b 0

:ChooseBranch
set "SELECTED_BRANCH=main"
set "DEFAULT_BRANCH_CHOICE=1"
where git >nul 2>&1
if errorlevel 1 exit /b 0

echo Checking available branches...
set "BRANCH_COUNT=0"
for /f "tokens=3 delims=/" %%b in ('git ls-remote --heads "%REPO_URL%" 2^>nul') do (
    if !BRANCH_COUNT! LSS 9 (
        set /a BRANCH_COUNT+=1
        set "BRANCH_!BRANCH_COUNT!=%%b"
        if /i "%%b"=="main" set "DEFAULT_BRANCH_CHOICE=!BRANCH_COUNT!"
    )
)

if !BRANCH_COUNT! EQU 0 (
    set "BRANCH_1=main"
    set "BRANCH_COUNT=1"
    set "DEFAULT_BRANCH_CHOICE=1"
)

echo.
echo %YELLOW%Choose branch to clone%RESET%
for /L %%i in (1,1,!BRANCH_COUNT!) do (
    if "%%i"=="!DEFAULT_BRANCH_CHOICE!" (
        call echo   [%%i] %%BRANCH_%%i%% ^(default^)
    ) else (
        call echo   [%%i] %%BRANCH_%%i%%
    )
)
echo.
echo Default branch: %GREEN%main%RESET%
choice /C 123456789 /D !DEFAULT_BRANCH_CHOICE! /T 5 /M "Choose branch number"
set "BRANCH_CHOICE=%ERRORLEVEL%"
if !BRANCH_CHOICE! GTR !BRANCH_COUNT! set "BRANCH_CHOICE=!DEFAULT_BRANCH_CHOICE!"
call set "SELECTED_BRANCH=%%BRANCH_!BRANCH_CHOICE!%%"
if "!SELECTED_BRANCH!"=="" set "SELECTED_BRANCH=main"
echo Selected branch: %GREEN%!SELECTED_BRANCH!%RESET%
echo.
exit /b 0

:ChooseClonePath
set "SECOND_DRIVE="
for %%d in (D E F G H) do (
    if exist %%d:\ (
        if "!SECOND_DRIVE!"=="" set "SECOND_DRIVE=%%d:"
    )
)
if "!SECOND_DRIVE!"=="" set "SECOND_DRIVE=C:"

echo %YELLOW%Choose install location%RESET%
echo.
echo   [1] C:\Coder\%PROJECT_FOLDER%
echo   [2] !SECOND_DRIVE!\%PROJECT_FOLDER%
echo   [3] %~dp0%PROJECT_FOLDER%
echo   [4] %USERPROFILE%\Documents\%PROJECT_FOLDER%
echo   [5] Custom parent folder
echo.
choice /C 12345 /D 1 /T 5 /M "Choose location"
set "CLONE_CHOICE=%ERRORLEVEL%"

if "!CLONE_CHOICE!"=="1" set "CLONE_PATH=C:\Coder"
if "!CLONE_CHOICE!"=="2" set "CLONE_PATH=!SECOND_DRIVE!\"
if "!CLONE_CHOICE!"=="3" set "CLONE_PATH=%~dp0"
if "!CLONE_CHOICE!"=="4" set "CLONE_PATH=%USERPROFILE%\Documents"
if "!CLONE_CHOICE!"=="5" (
    echo.
    set /p CUSTOM_PATH="Enter parent folder: "
    set "CLONE_PATH=!CUSTOM_PATH!"
)
if "!CLONE_PATH!"=="" set "CLONE_PATH=C:\Coder"

echo.
echo Install parent: %GREEN%!CLONE_PATH!%RESET%
echo.
exit /b 0

:EnsureUv
set "PATH=%USERPROFILE%\.local\bin;%LOCALAPPDATA%\Programs\uv;%PATH%"
uv --version >nul 2>&1
if not errorlevel 1 (
    uv python --help >nul 2>&1
    if errorlevel 1 (
        echo %YELLOW%uv is installed but too old for managed Python. Updating uv...%RESET%
        uv self update >nul 2>&1
        if errorlevel 1 powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    )
    uv python --help >nul 2>&1
    if errorlevel 1 (
        echo %RED%[ERROR] uv is available, but it does not support managed Python.%RESET%
        goto ErrorExit
    )
    for /f "tokens=*" %%u in ('uv --version') do echo %GREEN%%%u%RESET%
    exit /b 0
)

echo %YELLOW%uv was not found. Installing uv...%RESET%
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
if errorlevel 1 (
    echo %RED%[ERROR] Could not install uv.%RESET%
    goto ErrorExit
)

set "PATH=%USERPROFILE%\.local\bin;%LOCALAPPDATA%\Programs\uv;%PATH%"
uv --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR] uv was installed but is not available in PATH.%RESET%
    echo Close this window and run the launcher again.
    goto ErrorExit
)

uv python --help >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR] uv was installed, but it does not support managed Python.%RESET%
    goto ErrorExit
)

for /f "tokens=*" %%u in ('uv --version') do echo %GREEN%%%u%RESET%
exit /b 0

:EnsurePython
uv python find %PYTHON_VERSION% >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%p in ('uv python find %PYTHON_VERSION% 2^>nul') do echo %GREEN%Python ready:%RESET% %%p
    exit /b 0
)

echo %YELLOW%Python %PYTHON_VERSION% was not found. Installing managed Python with uv...%RESET%
uv python install %PYTHON_VERSION%
if errorlevel 1 (
    echo %RED%[ERROR] Could not install Python %PYTHON_VERSION%.%RESET%
    goto ErrorExit
)

for /f "tokens=*" %%p in ('uv python find %PYTHON_VERSION% 2^>nul') do echo %GREEN%Python ready:%RESET% %%p
exit /b 0

:AddKnownFfmpegPaths
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe" (
    set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;!PATH!"
)
for /d %%d in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*") do (
    for /d %%v in ("%%~fd\ffmpeg-*") do (
        if exist "%%~fv\bin\ffmpeg.exe" set "PATH=%%~fv\bin;!PATH!"
    )
)
for /d %%d in ("%ProgramFiles%\ffmpeg*") do (
    if exist "%%~fd\bin\ffmpeg.exe" set "PATH=%%~fd\bin;!PATH!"
)
for /d %%d in ("%ProgramFiles(x86)%\ffmpeg*") do (
    if exist "%%~fd\bin\ffmpeg.exe" set "PATH=%%~fd\bin;!PATH!"
)
exit /b 0

:EnsureFfmpeg
call :AddKnownFfmpegPaths
ffmpeg -version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%f in ('ffmpeg -version 2^>nul ^| findstr /b /c:"ffmpeg version"') do echo %GREEN%%%f%RESET%
    exit /b 0
)

echo %YELLOW%FFmpeg was not found. Trying to install FFmpeg with winget...%RESET%
winget --version >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%winget is not available, so FFmpeg cannot be installed automatically.%RESET%
    echo The app can still open, but MP3/audio conversion may fail until FFmpeg is installed.
    exit /b 0
)

winget install --id Gyan.FFmpeg --exact --source winget --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo %YELLOW%FFmpeg installation failed or was cancelled.%RESET%
    echo The app can still open, but MP3/audio conversion may fail until FFmpeg is installed.
    exit /b 0
)

call :AddKnownFfmpegPaths
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%FFmpeg was installed but is not visible in this window yet.%RESET%
    echo Close this window and run the launcher again if the app still warns about FFmpeg.
    exit /b 0
)

for /f "tokens=*" %%f in ('ffmpeg -version 2^>nul ^| findstr /b /c:"ffmpeg version"') do echo %GREEN%%%f%RESET%
exit /b 0
