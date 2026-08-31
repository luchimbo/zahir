param(
    [string]$Time = "03:00",
    [string]$TaskName = "PalermoKG-DailyRefresh"
)

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$runner = Join-Path $root "scripts\scheduled_refresh.py"
if (-not (Test-Path -LiteralPath $python)) { throw "No se encontró el entorno virtual: $python" }

$action = New-ScheduledTaskAction -Execute $python -Argument ('"{0}"' -f $runner) -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Ejecuta fuentes Palermo KG ya promovidas" -Force | Out-Null
Write-Output "Tarea '$TaskName' instalada para $Time."
