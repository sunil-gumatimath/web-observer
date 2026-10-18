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

# ---- Preflight: Redis (may run inside WSL2; reachable via localhost) --------
# Raw TcpClient probe: Test-NetConnection requires the NetTCPIP module,
# which can fail to load in some PowerShell sessions.
$RedisPort = 6379
$redisTest = $false
try {
    $redisProbe = New-Object System.Net.Sockets.TcpClient
    $redisProbe.Connect("127.0.0.1", $RedisPort)
    $redisTest = $redisProbe.Connected
    $redisProbe.Close()
} catch {
    $redisTest = $false
}
if ($redisTest) {
    Write-Host "Redis preflight: reachable on 127.0.0.1:$RedisPort" -ForegroundColor Green
} else {
    Write-Host "Redis preflight: NOT reachable on 127.0.0.1:$RedisPort (start it in WSL2; if Windows->WSL localhost forwarding is down, 'wsl --shutdown' then 'wsl' usually restores it)" -ForegroundColor Yellow
}

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

# ---- Helpers ----------------------------------------------------------------
function Test-ProcessAlive {
    param([string]$NamePattern, [string]$CmdPattern)
    $found = Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -match $NamePattern) -and ($_.CommandLine -match $CmdPattern)
    } | Select-Object -First 1
    return ($null -ne $found)
}

function Wait-ForUrl {
    # Poll a URL until it responds or the budget runs out. Returns $true on success.
    param(
        [string]$Url,
        [string]$Label,
        [int]$TimeoutSeconds,
        [hashtable]$AliveCheck   # optional: @{ Name=..; Cmd=.. } process liveness
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        # If a process check is wired up and the process already died, bail out
        # early with its stderr tail instead of polling a dead server.
        if ($AliveCheck -and -not (Test-ProcessAlive -NamePattern $AliveCheck.Name -CmdPattern $AliveCheck.Cmd)) {
            Write-Host "$Label : CRASHED - last error lines:" -ForegroundColor Red
            $errLog = Join-Path $LogDir $AliveCheck.ErrLog
            if (Test-Path $errLog) {
                Get-Content $errLog -Tail 8 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
            }
            return $false
        }
        try {
            Invoke-RestMethod -Uri $Url -TimeoutSec 5 | Out-Null
            Write-Host "$Label : OK" -ForegroundColor Green
            return $true
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    Write-Host "$Label : not responding after $TimeoutSeconds s (check logs in data\logs)" -ForegroundColor Yellow
    return $false
}

function Wait-Frontend {
    param([int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-ProcessAlive -NamePattern "bun" -CmdPattern "next dev")) {
            Write-Host "Frontend : CRASHED - last error lines:" -ForegroundColor Red
            $errLog = Join-Path $LogDir "frontend_err.log"
            if (Test-Path $errLog) {
                Get-Content $errLog -Tail 8 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
            }
            return $false
        }
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 5 -UseBasicParsing
            if ($resp.StatusCode -eq 200) {
                Write-Host "Frontend : OK" -ForegroundColor Green
                return $true
            }
        } catch {
            # 5xx responses land here too; keep polling until budget expires
        }
        Start-Sleep -Seconds 2
    }
    Write-Host "Frontend : not responding after $TimeoutSeconds s (check data\logs\frontend*.log)" -ForegroundColor Yellow
    return $false
}

Write-Host ""
Write-Host "=== Stack Status (waiting for services) ===" -ForegroundColor Green
# Honeywell-ish budgets: Neon cold start + DNS blips make first connect slow;
# the API health check earlier failed as a false negative at 3 s.
[void](Wait-ForUrl -Url "http://127.0.0.1:8002/health" -Label "API Health" -TimeoutSeconds 30 `
    -AliveCheck @{ Name = "uvicorn"; Cmd = "app\.main:app"; ErrLog = "api_err.log" })
[void](Wait-ForUrl -Url "http://127.0.0.1:8002/ready" -Label "DB Ready (Neon)" -TimeoutSeconds 60 `
    -AliveCheck @{ Name = "uvicorn"; Cmd = "app\.main:app"; ErrLog = "api_err.log" })
[void](Wait-Frontend -TimeoutSeconds 45)

Write-Host ""
Write-Host "App URLs:" -ForegroundColor White
Write-Host "  Frontend:  http://localhost:3000" -ForegroundColor Cyan
Write-Host "  API Docs:  http://127.0.0.1:8002/docs" -ForegroundColor Cyan
Write-Host "  Health:    http://127.0.0.1:8002/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "Logs: data\logs (api, worker-http, worker-browser, scheduler, frontend)" -ForegroundColor DarkGray
