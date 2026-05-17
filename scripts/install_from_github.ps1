param(
    [string]$InstallDir = "$env:USERPROFILE\ColinTTSLocal",
    [string]$RepoUrl = "https://github.com/colin-dmme/tts-voice-cloning-OMNI.git",
    [string]$ArchiveUrl = "https://github.com/colin-dmme/tts-voice-cloning-OMNI/archive/refs/heads/main.zip",
    [switch]$Web
)

$ErrorActionPreference = "Stop"

function Ensure-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        return
    }
    Write-Host "uv not found. Installing uv..."
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $userUv = Join-Path $env:USERPROFILE ".local\bin"
    if (Test-Path $userUv) {
        $env:Path = "$userUv;$env:Path"
    }
}

function Get-Source {
    $target = [System.IO.Path]::GetFullPath($InstallDir)
    if ((Test-Path (Join-Path $target ".git")) -and (Get-Command git -ErrorAction SilentlyContinue)) {
        Set-Location $target
        git pull --ff-only
        return $target
    }

    if ((Get-Command git -ErrorAction SilentlyContinue) -and -not (Test-Path $target)) {
        git clone $RepoUrl $target
        return $target
    }

    Write-Host "Git not found or target already exists without .git; downloading source archive..."
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("colin-tts-" + [guid]::NewGuid().ToString("N"))
    $zipPath = Join-Path $tempRoot "source.zip"
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $tempRoot -Force
    $expanded = Get-ChildItem -Path $tempRoot -Directory | Select-Object -First 1
    if (-not $expanded) {
        throw "Could not extract source archive."
    }
    if (Test-Path $target) {
        $existing = Get-ChildItem -LiteralPath $target -Force | Select-Object -First 1
        if ($existing) {
            throw "Target exists and is not empty: $target. Choose an empty InstallDir."
        }
        Copy-Item -Path (Join-Path $expanded.FullName "*") -Destination $target -Recurse -Force
    } else {
        Move-Item -LiteralPath $expanded.FullName -Destination $target
    }
    return $target
}

Ensure-Uv
$sourceDir = Get-Source
Set-Location $sourceDir

$args = @()
if ($Web) {
    $args += "-Web"
}
& (Join-Path $sourceDir "Start-ColinTTS.bat") @args
