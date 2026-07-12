# Start local stack without Docker (opens separate terminals on Windows).
# Prerequisites: Postgres + Redis on localhost, Python venv in backend\.venv

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
$VenvUvicorn = Join-Path $Backend ".venv\Scripts\uvicorn.exe"
$VenvDramatiq = Join-Path $Backend ".venv\Scripts\dramatiq.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Create venv first:"
    Write-Host "  cd backend; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

$envBlock = @"
`$env:DATABASE_URL = 'postgresql+psycopg://monitor:monitor@localhost:5432/web_observer'
`$env:REDIS_URL = 'redis://localhost:6379/0'
`$env:STORAGE_BACKEND = 'local'
`$env:LOCAL_STORAGE_PATH = '$Root\data\snapshots'
`$env:INTERNAL_API_TOKEN = 'dev-internal-token'
cd '$Backend'
"@

function Start-BackendWindow([string]$Title, [string]$Command) {
    $full = "$envBlock; Write-Host '=== $Title ===' -ForegroundColor Cyan; $Command"
    Start-Process powershell -ArgumentList @("-NoExit", "-Command", $full)
}

Write-Host "Starting API, worker, scheduler in new windows..." -ForegroundColor Green
Write-Host "Ensure Postgres and Redis are running on localhost." -ForegroundColor Yellow

Start-BackendWindow "API" "& '$VenvUvicorn' app.main:app --reload --host 127.0.0.1 --port 8000"
Start-Sleep -Seconds 1
Start-BackendWindow "Worker" "& '$VenvDramatiq' app.workers --queues http_checks notifications --processes 1 --threads 2"
Start-Sleep -Seconds 1
Start-BackendWindow "Scheduler" "& '$VenvPython' -m app.scheduler"

Write-Host ""
Write-Host "API:  http://127.0.0.1:8000/docs"
Write-Host "Then: cd frontend; npm run dev  -> http://localhost:3000"
Write-Host ""
Write-Host "Optional browser worker:"
Write-Host "  cd backend; .\.venv\Scripts\dramatiq app.workers --queues browser_checks --processes 1 --threads 1"
