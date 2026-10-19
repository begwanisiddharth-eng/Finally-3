# Stop the running FinAlly backend. See PLAN.md section 11.
# Never kills an unrelated PID; never deletes the database.
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$PidFile = if ($env:FINALLY_PID_FILE) { $env:FINALLY_PID_FILE } else { Join-Path $RepoRoot ".finally.pid" }

if (-not (Test-Path $PidFile)) {
    Write-Host "No PID file; FinAlly is not running."
    exit 0
}

$targetPid = (Get-Content $PidFile).Trim()
$proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
if ($proc) {
    Stop-Process -Id $targetPid -Force
    Write-Host "Stopped FinAlly (PID $targetPid)"
} else {
    Write-Host "PID $targetPid not running (stale PID file)"
}
Remove-Item $PidFile -Force
