param(
    [string]$OutputRoot = "dist_portable",
    [switch]$IncludeModels,
    [switch]$IncludeVoices,
    [switch]$IncludeEngineEnvs,
    [switch]$IncludeWorkerCaches,
    [switch]$SkipRuntime
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ResolvedOutputRoot = if ([System.IO.Path]::IsPathRooted($OutputRoot)) {
    $OutputRoot
} else {
    Join-Path $ProjectRoot $OutputRoot
}
$BuildRoot = Join-Path $ProjectRoot "build\portable"
$PortableRoot = Join-Path $ResolvedOutputRoot "colinttslocal"
$ObfuscatedSrc = Join-Path $BuildRoot "obfuscated_src"
$ObfuscatedWorkers = Join-Path $BuildRoot "obfuscated_workers"
$AppDir = Join-Path $PortableRoot "app"
$RuntimeDir = Join-Path $PortableRoot "runtime"
$RuntimePython = Join-Path $RuntimeDir "python"

function Copy-Directory {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [string[]]$ExcludeDirs = @(),
        [string[]]$ExcludeFiles = @()
    )

    if (!(Test-Path -LiteralPath $Source)) {
        throw "Missing source: $Source"
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $args = @(
        $Source,
        $Destination,
        "/E",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NP",
        "/R:2",
        "/W:2"
    )
    if ($ExcludeDirs.Count -gt 0) {
        $args += "/XD"
        $args += $ExcludeDirs
    }
    if ($ExcludeFiles.Count -gt 0) {
        $args += "/XF"
        $args += $ExcludeFiles
    }
    & robocopy @args | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed from $Source to $Destination with exit code $LASTEXITCODE"
    }
    $global:LASTEXITCODE = 0
}

function Read-VenvHome {
    param([Parameter(Mandatory = $true)][string]$VenvCfg)
    $line = Get-Content -LiteralPath $VenvCfg | Where-Object { $_ -match "^home\s*=" } | Select-Object -First 1
    if (!$line) {
        throw "Cannot find Python home in $VenvCfg"
    }
    return ($line -replace "^home\s*=\s*", "").Trim()
}

function Write-Runner {
    $runner = Join-Path $PortableRoot "colinttslocal.bat"
    @'
@echo off
setlocal
cd /d "%~dp0"

set COLIN_TTS_ROOT=%~dp0
set OMNI_TTS_LICENSE_PUBLIC_KEY=%~dp0config\license_public_key.pem
set HF_HOME=%~dp0.hf_cache
set HF_HUB_CACHE=%~dp0.hf_cache\hub
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set PYTHONPATH=%~dp0app;%~dp0app\src
set PATH=%~dp0runtime\python;%~dp0runtime\python\DLLs;%PATH%

echo Starting Colin TTS Local...
"%~dp0runtime\python\python.exe" -m omni_tts_ui_tkinter.main

if errorlevel 1 (
  echo.
  echo Colin TTS Local stopped with an error.
  pause
)
'@ | Set-Content -LiteralPath $runner -Encoding ASCII
}

function Write-CustomerReadme {
    $readme = Join-Path $PortableRoot "README_FIRST.txt"
    @'
Colin TTS Local portable

1. Double-click colinttslocal.bat to open the app.
2. Open the Ban quyen tab and copy the machine code.
3. Send that machine code to the software owner to receive license.json.
4. In the app, click Nhap file license and choose license.json.
5. After activation, use the app normally.

Do not move files out of this folder. If Windows blocks the zip, right-click the zip, choose Properties, and unblock it before extracting.
'@ | Set-Content -LiteralPath $readme -Encoding UTF8
}

function Copy-Config {
    $target = Join-Path $PortableRoot "config"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "config\app.yaml") -Destination $target -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "config\models.yaml") -Destination $target -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "config\license_public_key.pem") -Destination $target -Force
}

function Copy-MainRuntime {
    if ($SkipRuntime) {
        Write-Host "Skipping runtime copy."
        return
    }

    $venv = Join-Path $ProjectRoot ".venv"
    $pythonHome = Read-VenvHome (Join-Path $venv "pyvenv.cfg")
    Write-Host "Copying Python runtime..."
    Copy-Directory -Source $pythonHome -Destination $RuntimePython -ExcludeDirs @("__pycache__")

    Write-Host "Copying main site-packages..."
    $sitePackages = Join-Path $RuntimePython "Lib\site-packages"
    Copy-Directory `
        -Source (Join-Path $venv "Lib\site-packages") `
        -Destination $sitePackages `
        -ExcludeDirs @("__pycache__", "pip", "pip-*", "setuptools", "setuptools-*") `
        -ExcludeFiles @("__editable__*", "_editable_impl_*.pth")
}

function Build-ObfuscatedSource {
    Write-Host "Obfuscating src..."
    if (Test-Path -LiteralPath $ObfuscatedSrc) {
        Remove-Item -LiteralPath $ObfuscatedSrc -Recurse -Force
    }
    & uvx pyarmor gen -O $ObfuscatedSrc -r (Join-Path $ProjectRoot "src")
    if ($LASTEXITCODE -ne 0) {
        throw "PyArmor failed for src"
    }

    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    Copy-Directory -Source (Join-Path $ObfuscatedSrc "src") -Destination (Join-Path $AppDir "src")
    Copy-Directory -Source (Join-Path $ObfuscatedSrc "pyarmor_runtime_000000") -Destination (Join-Path $AppDir "pyarmor_runtime_000000")
}

function Build-Worker {
    param(
        [Parameter(Mandatory = $true)][string]$Name
    )
    $sourceDir = Join-Path $ProjectRoot "engines\$Name"
    $targetDir = Join-Path $PortableRoot "engines\$Name"
    $workerBuild = Join-Path $ObfuscatedWorkers $Name

    Write-Host "Preparing worker $Name..."
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Copy-Item -LiteralPath (Join-Path $sourceDir "README.md") -Destination $targetDir -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath (Join-Path $sourceDir "pyproject.toml") -Destination $targetDir -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath (Join-Path $sourceDir "uv.lock") -Destination $targetDir -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath (Join-Path $sourceDir "vendor")) {
        Copy-Directory `
            -Source (Join-Path $sourceDir "vendor") `
            -Destination (Join-Path $targetDir "vendor") `
            -ExcludeDirs @(".git", "__pycache__")
    }
    if (Test-Path -LiteralPath (Join-Path $sourceDir "pretrained")) {
        Copy-Directory `
            -Source (Join-Path $sourceDir "pretrained") `
            -Destination (Join-Path $targetDir "pretrained") `
            -ExcludeDirs @("__pycache__")
    }

    if (Test-Path -LiteralPath $workerBuild) {
        Remove-Item -LiteralPath $workerBuild -Recurse -Force
    }
    & uvx pyarmor gen -O $workerBuild (Join-Path $sourceDir "synthesize.py")
    if ($LASTEXITCODE -ne 0) {
        throw "PyArmor failed for worker $Name"
    }
    Copy-Item -LiteralPath (Join-Path $workerBuild "synthesize.py") -Destination $targetDir -Force
    Copy-Directory -Source (Join-Path $workerBuild "pyarmor_runtime_000000") -Destination (Join-Path $targetDir "pyarmor_runtime_000000")

    if ($IncludeEngineEnvs) {
        Write-Host "Copying worker site-packages for $Name..."
        $workerVenv = Join-Path $sourceDir ".venv"
        Copy-Directory `
            -Source (Join-Path $workerVenv "Lib\site-packages") `
            -Destination (Join-Path $targetDir "site-packages") `
            -ExcludeDirs @("__pycache__", "pip", "pip-*", "setuptools", "setuptools-*") `
            -ExcludeFiles @("__editable__*", "_editable_impl_*.pth")
        if (Test-Path -LiteralPath (Join-Path $workerVenv "share")) {
            Copy-Directory -Source (Join-Path $workerVenv "share") -Destination (Join-Path $targetDir "share")
        }
    }
}

function Copy-HfCacheRepo {
    param([Parameter(Mandatory = $true)][string]$RepoDirName)
    $source = Join-Path $ProjectRoot ".hf_cache\hub\$RepoDirName"
    if (!(Test-Path -LiteralPath $source)) {
        Write-Host "Skipping missing cache: $RepoDirName"
        return
    }
    $target = Join-Path $PortableRoot ".hf_cache\hub\$RepoDirName"
    Copy-Directory -Source $source -Destination $target -ExcludeDirs @("__pycache__")
}

function Copy-WorkerCaches {
    Write-Host "Copying worker model caches..."
    New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot ".hf_cache\hub") | Out-Null
    $workerRepos = @(
        "models--neuphonic--distill-neucodec",
        "models--neuphonic--neucodec-onnx-decoder-int8",
        "models--nguyen-brat--nguyen-ngoc-ngan-vieneu-tts-fine-tune",
        "models--pnnbao-ump--VieNeu-Codec",
        "models--pnnbao-ump--VieNeu-TTS-0.3B-q4-gguf",
        "models--pnnbao-ump--VieNeu-TTS-0.3B-q8-gguf",
        "models--pnnbao-ump--VieNeu-TTS-v2",
        "models--pnnbao-ump--VieNeu-TTS-v2-Turbo-GGUF"
    )
    foreach ($repo in $workerRepos) {
        Copy-HfCacheRepo -RepoDirName $repo
    }
    $valtecAppData = Join-Path $ProjectRoot ".hf_cache\valtec_appdata"
    if (Test-Path -LiteralPath $valtecAppData) {
        Copy-Directory `
            -Source $valtecAppData `
            -Destination (Join-Path $PortableRoot ".hf_cache\valtec_appdata") `
            -ExcludeDirs @("__pycache__")
    }
}

Write-Host "Building Colin TTS Local portable at $PortableRoot"
if (Test-Path -LiteralPath $PortableRoot) {
    Remove-Item -LiteralPath $PortableRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $PortableRoot | Out-Null
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null

Build-ObfuscatedSource
Copy-Config
Copy-MainRuntime
Build-Worker -Name "vieneu_worker"
Build-Worker -Name "qwen_worker"
Build-Worker -Name "valtec_worker"

New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot "models") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot "voices") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot "outputs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot ".hf_cache") | Out-Null

if ($IncludeModels) {
    Write-Host "Copying models..."
    Copy-Directory -Source (Join-Path $ProjectRoot "models") -Destination (Join-Path $PortableRoot "models")
}

if ($IncludeVoices) {
    Write-Host "Copying voices..."
    Copy-Directory -Source (Join-Path $ProjectRoot "voices") -Destination (Join-Path $PortableRoot "voices")
}

if ($IncludeWorkerCaches) {
    Copy-WorkerCaches
}

Write-Runner
Write-CustomerReadme

Write-Host ""
Write-Host "Portable build created:"
Write-Host $PortableRoot
Write-Host ""
Write-Host "For a customer-ready full package, run with:"
Write-Host ".\packaging\build_portable.ps1 -IncludeModels -IncludeVoices -IncludeEngineEnvs"
Write-Host ""
Write-Host "For a lighter package, omit -IncludeModels and add -IncludeWorkerCaches."
