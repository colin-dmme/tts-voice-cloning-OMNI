param(
    [switch]$NoPush,
    [string]$Message = "Sync portable user state"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Run Start-ColinTTS.bat once, or install uv first."
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is required to commit and push user_state."
}

Write-Host "Exporting current profiles and shared settings to user_state..."
uv run python scripts\export_user_state.py

git add user_state
$changes = git status --porcelain -- user_state
if (-not $changes) {
    Write-Host "No user_state changes to commit."
    exit 0
}

git commit -m $Message -- user_state

if ($NoPush) {
    Write-Host "Committed user_state locally. Push skipped."
    exit 0
}

$branch = (git branch --show-current).Trim()
if (-not $branch) {
    throw "Cannot determine current branch."
}
git push origin $branch
