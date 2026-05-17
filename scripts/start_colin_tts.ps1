param(
    [switch]$Web,
    [switch]$NoPull,
    [switch]$SkipRestore,
    [switch]$ForceState
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

function Ensure-Uv {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        return
    }

    Write-Host "uv not found. Installing uv..."
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $userUv = Join-Path $env:USERPROFILE ".local\bin"
    if (Test-Path $userUv) {
        $env:Path = "$userUv;$env:Path"
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv installed but is not available in PATH. Open a new terminal and run Start-ColinTTS.bat again."
    }
}

function Pull-Latest {
    if ($NoPull) {
        return
    }
    if (-not (Test-Path ".git")) {
        return
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "Git not found; skipping pull."
        return
    }

    Write-Host "Pulling latest source..."
    git pull --ff-only
}

function Ensure-DesktopShortcut {
    $desktop = [Environment]::GetFolderPath("Desktop")
    if (-not $desktop) {
        return
    }
    $shortcutPath = Join-Path $desktop "Colin TTS Local.lnk"
    $targetPath = Join-Path $ProjectRoot "Start-ColinTTS.bat"
    if (-not (Test-Path $targetPath)) {
        return
    }

    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $targetPath
        $shortcut.WorkingDirectory = $ProjectRoot
        $shortcut.Description = "Open Colin TTS Local"
        $shortcut.IconLocation = "$env:SystemRoot\System32\SHELL32.dll,220"
        $shortcut.Save()
        Write-Host "Desktop shortcut ready: $shortcutPath"
    } catch {
        Write-Host "Could not create desktop shortcut: $($_.Exception.Message)"
    }
}

Ensure-Uv
Pull-Latest
Ensure-DesktopShortcut

$env:HF_HOME = Join-Path $ProjectRoot ".hf_cache"
$env:HF_HUB_CACHE = Join-Path $ProjectRoot ".hf_cache\hub"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

Write-Host "Preparing Python environment..."
uv sync --inexact

if (-not $SkipRestore) {
    Write-Host "Restoring Git-backed user state..."
    $restoreArgs = @("run", "--no-sync", "python", "scripts\restore_user_state.py")
    if ($ForceState) {
        $restoreArgs += "--force"
        $restoreArgs += "--force-settings"
    }
    uv @restoreArgs
}

if ($Web) {
    Write-Host "Starting Colin TTS Local web UI..."
    uv run --no-sync omni-tts-gradio
} else {
    Write-Host "Starting Colin TTS Local desktop UI..."
    uv run --no-sync omni-tts-tkinter
}
