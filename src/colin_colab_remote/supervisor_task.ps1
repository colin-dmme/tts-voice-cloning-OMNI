param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$Project,
    [Parameter(Mandatory=$true)][string]$DataDirectory,
    [ValidateSet('enable','disable')][string]$Mode
)
$ErrorActionPreference = 'Stop'
$taskName = 'Colin TTS Colab Supervisor'
$taskArguments = '-m colin_colab_remote.daemon --data-dir "' + $DataDirectory + '"'
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Actions.Count -ne 1 -or $existing.Actions[0].Execute -ne $Python -or
        $existing.Actions[0].WorkingDirectory -ne $Project -or
        $existing.Actions[0].Arguments -ne $taskArguments) {
        throw 'The existing task belongs to a different launcher. Review it before replacing.'
    }
}
if ($Mode -eq 'disable') {
    if ($existing) { Disable-ScheduledTask -TaskName $taskName | Out-Null }
    exit 0
}
$action = New-ScheduledTaskAction -Execute $Python -Argument $taskArguments -WorkingDirectory $Project
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal `
    -Settings $settings -Description 'Colin TTS managed Colab queue and app-owned runtime recovery.' -Force | Out-Null
