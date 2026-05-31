# watchdog.ps1 — ensures agent.py is always running
# Triggered by Task Scheduler every 5 minutes under SYSTEM

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python    = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $python) { exit 1 }

$agentRunning = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match [regex]::Escape("agent.py") }

if (-not $agentRunning) {
    Start-Process $python -ArgumentList "`"$ScriptDir\agent.py`"" -WindowStyle Hidden
}
