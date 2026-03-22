$batPath = Join-Path $PSScriptRoot "run_digest.bat"
$workDir = $PSScriptRoot

$action = New-ScheduledTaskAction -Execute $batPath -WorkingDirectory $workDir
$trigger = New-ScheduledTaskTrigger -Daily -At "6:00PM"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Unregister-ScheduledTask -TaskName "PMJobDigest" -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "PMJobDigest" -Action $action -Trigger $trigger -Settings $settings

Write-Host "Task updated. Next run:"
(Get-ScheduledTaskInfo -TaskName "PMJobDigest") | Select-Object NextRunTime, LastTaskResult | Format-List
