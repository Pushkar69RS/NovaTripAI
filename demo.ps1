param([int]$Port = 8080)
# Travel Yantra — one double-click to a demo-ready landing page.
# Kills whatever holds the port, runs scripts/demo_up.py, starts the server in
# its own window (log in var/server.log), waits for /health, opens the browser.
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

$holders = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($holder in $holders) {
    Write-Host "Stopping the server already on port $Port (PID $holder)"
    taskkill /PID $holder /F | Out-Null
}
if ($holders) { Start-Sleep -Seconds 1 }

Write-Host "Setting up the demo..."
uv run python scripts/demo_up.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Setup stopped; fix the message above and run again."
    exit 1
}

New-Item -ItemType Directory -Force -Path "var" | Out-Null
$serverCommand = "`$Host.UI.RawUI.WindowTitle = 'Travel Yantra server'; Set-Location '$PSScriptRoot'; " +
    "uv run uvicorn app.main:app --port $Port 2>&1 | Tee-Object -FilePath 'var\server.log'"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $serverCommand | Out-Null

$deadline = (Get-Date).AddSeconds(30)
$up = $false
while ((Get-Date) -lt $deadline) {
    try {
        $reply = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        if ($reply.StatusCode -eq 200) { $up = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
}
if (-not $up) {
    Write-Host "server did not come up — read var/server.log"
    exit 1
}
Write-Host "Server up on http://127.0.0.1:$Port/"
Start-Process "http://127.0.0.1:$Port/"

Write-Host ""
Write-Host "Cue sheet:"
Get-Content "var\cue.txt"
