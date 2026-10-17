param([switch]$StartBroker)

$ErrorActionPreference = "Stop"
$studioRoot = Split-Path -Parent $PSScriptRoot
$profilePath = Join-Path $studioRoot "config\remote_compute_workers.json"

try {
    if ($StartBroker) {
        $controlPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $controlPython)) { throw 'Open run_qt.bat once to install the Studio runtime.' }
        & $controlPython -m omni_tts_core.remote_compute.local_broker start
        if ($LASTEXITCODE -ne 0) { throw 'Could not start the background broker. Open Manage-Compute-Broker.vbs for status.' }
    }
    $config = [System.IO.File]::ReadAllText($profilePath) | ConvertFrom-Json
    $selected = @($config.profiles | Where-Object enabled | Select-Object -First 1)[0]
    if (-not $selected) { throw "No enabled worker profile is configured." }
    $token = [System.IO.File]::ReadAllText($selected.auth_token_file).Trim()
    $headers = @{Authorization = "Bearer $token"; "User-Agent" = "Colin-TTS-Studio/0.5"}
    $health = Invoke-RestMethod -Uri "$($selected.broker_url)/health" -Headers $headers -TimeoutSec 20
    $workers = @(Invoke-RestMethod -Uri "$($selected.broker_url)/v1/workers" -Headers $headers -TimeoutSec 20)
    Write-Host "Broker: $($health.status) - $($selected.broker_url)"
    Write-Host "Selected worker: $($config.selection.selected_profile_id)"
    Write-Host "Switch policy: $($config.selection.switch_policy)"
    foreach ($profile in $config.profiles) {
        $worker = $workers | Where-Object { $_.capabilities.worker_id -eq $profile.worker_id } | Select-Object -First 1
        $state = "OFFLINE - start this account's Colab notebook"
        if ($worker) {
            $age = ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($worker.last_seen_at)).TotalSeconds
            if ($age -ge 0 -and $age -le 120) { $state = "ONLINE" }
        }
        if (-not $profile.enabled) { $state = "DISABLED" }
        Write-Host "$($profile.worker_id): $state"
    }
    Write-Host "Local CPU generation also works without Colab. Open run_qt.bat to use Studio."
} catch {
    Write-Host "Check failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "See HUONG-DAN-BAT-DAU-LAI.md in the Studio folder."
    exit 1
}
