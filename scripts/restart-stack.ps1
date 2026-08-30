# Web Observer Stack Launcher (Windows / PowerShell)
# Starts: API (:8002), Dramatiq HTTP Worker, Dramatiq Browser Worker, Scheduler, and Frontend (:3000 with Bun)
$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$LogDir = Join-Path $RootDir "data\logs"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

Write-Host "Stopping any existing Web Observer backend/frontend processes..." -ForegroundColor Yellow
Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -match "python|dramatiq|uvicorn|bun|node") -and 
    ($_.CommandLine -match "monitor-the-web|uvicorn|dramatiq|app\.scheduler|next dev|WO-")
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

try {
    $pidsToKill = Get-NetTCPConnection -LocalPort 8002,3000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in $pidsToKill) {
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    }
} catch {
    # Ignore if NetTCPIP cmdlet unavailable
}

Start-Sleep -Seconds 1

$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
$UvicornExe = Join-Path $BackendDir ".venv\Scripts\uvicorn.exe"
$DramatiqExe = Join-Path $BackendDir ".venv\Scripts\dramatiq.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Virtual environment not found at $BackendDir\.venv. Please create it first."
    exit 1
}

Write-Host "Starting API on http://127.0.0.1:8002..." -ForegroundColor Cyan
Start-Process -FilePath $UvicornExe -ArgumentList "app.main:app --host 127.0.0.1 --port 8002" -WorkingDirectory $BackendDir -RedirectStandardOutput (Join-Path $LogDir "api.log") -RedirectStandardError (Join-Path $LogDir "api_err.log") -WindowStyle Hidden

Write-Host "Starting HTTP + Notifications Dramatiq Worker..." -ForegroundColor Cyan
Start-Process -FilePath $DramatiqExe -ArgumentList "app.workers --queues http_checks notifications --processes 1 --threads 2" -WorkingDirectory $BackendDir -RedirectStandardOutput (Join-Path $LogDir "worker-http.log") -RedirectStandardError (Join-Path $LogDir "worker-http_err.log") -WindowStyle Hidden

Write-Host "Starting Browser Dramatiq Worker..." -ForegroundColor Cyan
Start-Process -FilePath $DramatiqExe -ArgumentList "app.workers --queues browser_checks --processes 1 --threads 1" -WorkingDirectory $BackendDir -RedirectStandardOutput (Join-Path $LogDir "worker-browser.log") -RedirectStandardError (Join-Path $LogDir "worker-browser_err.log") -WindowStyle Hidden

Write-Host "Starting Scheduler..." -ForegroundColor Cyan
Start-Process -FilePath $PythonExe -ArgumentList "-m app.scheduler" -WorkingDirectory $BackendDir -RedirectStandardOutput (Join-Path $LogDir "scheduler.log") -RedirectStandardError (Join-Path $LogDir "scheduler_err.log") -WindowStyle Hidden

Write-Host "Starting Frontend on http://localhost:3000 with Bun..." -ForegroundColor Cyan
Start-Process -FilePath "bun" -ArgumentList "run dev --port 3000" -WorkingDirectory $FrontendDir -RedirectStandardOutput (Join-Path $LogDir "frontend.log") -RedirectStandardError (Join-Path $LogDir "frontend_err.log") -WindowStyle Hidden

Start-Sleep -Seconds 3

Write-Host "`n=== Stack Status ===" -ForegroundColor Green
try {
    $apiHealth = Invoke-RestMethod -Uri "http://127.0.0.1:8002/health" -TimeoutSec 5
    Write-Host "API Health: OK (v$($apiHealth.version))" -ForegroundColor Green
} catch {
    Write-Host "API Health: Waiting/Starting... ($($_))" -ForegroundColor Yellow
}

try {
    $apiReady = Invoke-RestMethod -Uri "http://127.0.0.1:8002/ready" -TimeoutSec 5
    Write-Host "DB Ready: OK (v$($apiReady.version))" -ForegroundColor Green
} catch {
    Write-Host "DB Ready: Waiting/Starting... ($($_))" -ForegroundColor Yellow
}

Write-Host "`nApp URLs:" -ForegroundColor White
Write-Host "  Frontend:  http://localhost:3000" -ForegroundColor Cyan
Write-Host "  API Docs:  http://127.0.0.1:8002/docs" -ForegroundColor Cyan
Write-Host "  Health:    http://127.0.0.1:8002/health" -ForegroundColor Cyan
