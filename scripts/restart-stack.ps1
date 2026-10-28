# Web Observer Stack Launcher (Windows / PowerShell)
# Starts: Frontend (:3000 with Bun), API (:8002), Dramatiq HTTP Worker,
#         Dramatiq Browser Worker, Scheduler
#
# Port handling: if a requested port is held by an app we may not kill, the
# stack moves to the next free port automatically and stays fully wired up
# (the API CORS allow-list and the frontend's API base URL are both updated).
param(
    # Preferred frontend dev-server port.
    [int]$FrontendPort = 3000,
    # Preferred API port. Must match NEXT_PUBLIC_API_BASE_URL in frontend\.env.local
    # unless the stack shifts it (it then rewrites the value for the dev server).
    [int]$ApiPort = 8002
)

$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$LogDir = Join-Path $RootDir "data\logs"
$StateFile = Join-Path $LogDir "our-processes.txt"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# ---------------------------------------------------------------------------
# Process bookkeeping
#
# Every process this script starts is recorded in $StateFile (one PID per
# line). On the next run the recorded PIDs - plus any process orphaned by a
# dead parent (Dramatiq's forked workers) - are stopped.
#
# This is deliberately narrow: a foreign app that owns port 3000 (another
# Next.js project, say) is NEVER killed, because it is not in our records and
# its command line does not point at this repository.
# ---------------------------------------------------------------------------
function Get-TrackedProcessIds {
    if (-not (Test-Path $StateFile)) { return @() }
    $ids = @()
    foreach ($line in (Get-Content $StateFile -ErrorAction SilentlyContinue)) {
        $t = $line.Trim()
        if ($t -match '^\d+$') { $ids += [int]$t }
    }
    return $ids
}

function Get-ProcessSnapshot {
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
}

function Get-DescendantProcessIds {
    param([int]$RootProcessId, [array]$Snapshot)
    $found = @()
    $queue = @($RootProcessId)
    while ($queue.Count -gt 0) {
        $current = $queue[0]
        $queue = @($queue | Select-Object -Skip 1)
        foreach ($child in @($Snapshot | Where-Object { $_.ParentProcessId -eq $current })) {
            $found += $child.ProcessId
            $queue += $child.ProcessId
        }
    }
    return $found
}

function Stop-ProcessTreeById {
    param([int]$RootProcessId)
    $snapshot = Get-ProcessSnapshot
    $ids = @(Get-DescendantProcessIds -RootProcessId $RootProcessId -Snapshot $snapshot)
    # Deepest first so a parent cannot respawn a child we just killed.
    [array]::Reverse($ids)
    foreach ($id in $ids) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
}

function Get-AncestorProcessIds {
    # The current process and its ancestors - never kill these.
    param([int]$ProcessId, [array]$Snapshot)
    $ids = @()
    $current = $ProcessId
    while ($current -gt 0) {
        $ids += $current
        $proc = $Snapshot | Where-Object { $_.ProcessId -eq $current } | Select-Object -First 1
        if (-not $proc) { break }
        $current = [int]$proc.ParentProcessId
    }
    return $ids
}

function Stop-TrackedProcesses {
    $tracked = @(Get-TrackedProcessIds)
    if ($tracked.Count -eq 0) { return }
    $snapshot = Get-ProcessSnapshot
    $protect = @(Get-AncestorProcessIds -ProcessId $PID -Snapshot $snapshot)

    $victims = @()
    foreach ($p in $snapshot) {
        if ($protect -contains $p.ProcessId) { continue }
        if ($tracked -contains $p.ProcessId) {
            # A recorded PID may have been REUSED by an unrelated process since
            # it was recorded. Only kill it if it still looks like ours.
            $looksOurs = ($p.CommandLine -match "monitor-the-web") -or ($tracked -contains $p.ParentProcessId)
            if ($looksOurs) { $victims += $p.ProcessId }
            continue
        }
        # Orphaned worker whose parent was recorded but has since died.
        if ($tracked -contains $p.ParentProcessId) { $victims += $p.ProcessId }
    }

    $killed = 0
    foreach ($id in ($victims | Select-Object -Unique)) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        $killed++
    }
    if ($killed -gt 0) { Write-Host "  Stopped $killed process(es) from the previous run" -ForegroundColor DarkGray }
}

function Save-TrackedProcessIds {
    param([array]$RootProcessIds)
    $snapshot = Get-ProcessSnapshot
    $ids = @()
    foreach ($root in $RootProcessIds) {
        if ($snapshot | Where-Object { $_.ProcessId -eq $root }) { $ids += $root }
        $ids += @(Get-DescendantProcessIds -RootProcessId $root -Snapshot $snapshot)
    }
    $ids | Select-Object -Unique | Where-Object { $_ -gt 0 } | Set-Content -Path $StateFile -Encoding ASCII
}

# ---------------------------------------------------------------------------
# Port helpers
#
# netstat is the source of truth for "is this port taken": a TcpListener bind
# check is NOT reliable on Windows, where a second socket can bind a port that
# is already being served (SO_REUSEADDR).
# ---------------------------------------------------------------------------
function Get-PortOwner {
    param([int]$Port)
    $pids = @()
    foreach ($line in (netstat -ano)) {
        $parts = ($line -split '\s+') | Where-Object { $_ -ne '' }
        # TCP <local> <remote> LISTENING <pid>
        if ($parts.Count -lt 5) { continue }
        if ($parts[0] -ne 'TCP') { continue }
        if ($parts[3] -ne 'LISTENING') { continue }
        if ($parts[1] -notmatch ":$Port$") { continue }
        if ($parts[4] -match '^\d+$') { $pids += [int]$parts[4] }
    }
    if ($pids.Count -eq 0) {
        # Fallback via the NetTCPIP module (netstat parsing above wins).
        try {
            $pids = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
                    Select-Object -ExpandProperty OwningProcess -Unique)
        } catch {
            $pids = @()
        }
    }
    return $pids
}

function Test-PortFree {
    param([int]$Port)
    return (@(Get-PortOwner -Port $Port).Count -eq 0)
}

function Get-NextFreePort {
    param([int]$Port, [int]$MaxTries = 20)
    for ($candidate = $Port; $candidate -lt ($Port + $MaxTries); $candidate++) {
        if (Test-PortFree -Port $candidate) { return $candidate }
    }
    return $Port
}

# A port owner is "ours" when it is one of our tracked processes or when it
# runs from this repository. Anything else belongs to another app.
function Test-OurPortOwner {
    param([int]$Port)
    $tracked = @(Get-TrackedProcessIds)
    $snapshot = Get-ProcessSnapshot
    foreach ($p in (@(Get-PortOwner -Port $Port) | Select-Object -Unique)) {
        if ($tracked -contains $p) { return $true }
        $proc = $snapshot | Where-Object { $_.ProcessId -eq $p }
        if ($proc -and $proc.CommandLine -match "monitor-the-web") { return $true }
    }
    return $false
}

function Stop-OurPortOwner {
    param([int]$Port)
    foreach ($p in (@(Get-PortOwner -Port $Port) | Select-Object -Unique)) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $p" -ErrorAction SilentlyContinue
        $cmd = if ($proc) { "$($proc.Name) $($proc.CommandLine)" } else { "" }
        if (Test-OurPortOwner -Port $Port) {
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
            Write-Host "  Freed port $Port (our process, PID $p)" -ForegroundColor DarkGray
        } else {
            Write-Host "  Port $Port is held by another app (PID $p): $cmd" -ForegroundColor Yellow
            Write-Host "  Left running - the stack will move to the next free port." -ForegroundColor Yellow
        }
    }
}

# ---------------------------------------------------------------------------
# Process starting
# ---------------------------------------------------------------------------
function Start-PersistentProcess {
    # Returns the PID of the launcher process so the whole tree can be tracked.
    param(
        [string]$FilePath,
        [string]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$StdOutPath,
        [string]$StdErrPath
    )
    $cmd = "cmd.exe /c `"`"$FilePath`" $ArgumentList 1>`"$StdOutPath`" 2>`"$StdErrPath`"`""
    try {
        $proc = [wmiclass]"Win32_Process"
        $startup = [wmiclass]"Win32_ProcessStartup"
        $startupConfig = $startup.CreateInstance()
        $startupConfig.ShowWindow = 0 # 0 = SW_HIDE (silent background window)
        $res = $proc.Create($cmd, $WorkingDirectory, $startupConfig)
        if ($res.ReturnValue -ne 0) {
            $p = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $StdOutPath -RedirectStandardError $StdErrPath -WindowStyle Hidden -PassThru
            return $p.Id
        }
        return $res.ProcessId
    } catch {
        $p = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $StdOutPath -RedirectStandardError $StdErrPath -WindowStyle Hidden -PassThru
        return $p.Id
    }
}

function Test-ProcessAlive {
    param([string]$NamePattern, [string]$CmdPattern)
    $found = Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -match $NamePattern) -and
        ($_.CommandLine -match $CmdPattern)
    } | Select-Object -First 1
    return ($null -ne $found)
}

function Test-PortOwnedByUs {
    param([int]$Port)
    $tracked = @(Get-TrackedProcessIds)
    $snapshot = Get-ProcessSnapshot
    foreach ($p in (@(Get-PortOwner -Port $Port) | Select-Object -Unique)) {
        if ($tracked -contains $p) { return $true }
        $proc = $snapshot | Where-Object { $_.ProcessId -eq $p }
        if ($proc -and $proc.CommandLine -match "monitor-the-web") { return $true }
    }
    return $false
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
    param([int]$TimeoutSeconds, [int]$RootProcessId = 0)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        # Our own launcher process gone => the dev server died; fail fast so
        # the caller can retry on another port.
        if ($RootProcessId -gt 0) {
            $root = Get-CimInstance Win32_Process -Filter "ProcessId = $RootProcessId" -ErrorAction SilentlyContinue
            if (-not $root) {
                Write-Host "Frontend : dev server exited" -ForegroundColor Red
                $errLog = Join-Path $LogDir "frontend_err.log"
                if (Test-Path $errLog) {
                    Get-Content $errLog -Tail 5 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
                }
                return $false
            }
        }
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:$FrontendPort" -TimeoutSec 5 -UseBasicParsing
            if ($resp.StatusCode -eq 200) {
                # Guard against another app squatting on the port: only a port
                # served by one of our own processes counts as "the frontend is up".
                if (-not (Test-PortOwnedByUs -Port $FrontendPort)) {
                    Write-Host "Frontend : port $FrontendPort is served by another app - waiting..." -ForegroundColor Yellow
                    Start-Sleep -Seconds 2
                    continue
                }
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

# ===========================================================================
# Run
# ===========================================================================
Write-Host "Stopping any existing Web Observer backend/frontend processes..." -ForegroundColor Yellow
Stop-TrackedProcesses

# Also catch processes started manually from this repo (e.g. a stray `next dev`
# in the frontend folder). The path check keeps foreign apps untouched.
$snapshot = Get-ProcessSnapshot
$protect = @(Get-AncestorProcessIds -ProcessId $PID -Snapshot $snapshot)
foreach ($p in $snapshot) {
    if ($p.Name -notmatch "python|dramatiq|uvicorn|bun|node|cmd") { continue }
    if ($p.CommandLine -notmatch "monitor-the-web") { continue }
    if ($p.CommandLine -match "restart-stack\.ps1") { continue }
    if ($protect -contains $p.ProcessId) { continue }
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "  Cleaning ports $ApiPort / $FrontendPort..." -ForegroundColor DarkGray
Stop-OurPortOwner -Port $ApiPort
Stop-OurPortOwner -Port $FrontendPort

Start-Sleep -Seconds 1

# ---- Port selection --------------------------------------------------------
if (-not (Test-PortFree -Port $ApiPort)) {
    $shifted = Get-NextFreePort -Port ($ApiPort + 1)
    Write-Host "  API port $ApiPort is taken -> moving to $shifted" -ForegroundColor Yellow
    $ApiPort = $shifted
}
if (-not (Test-PortFree -Port $FrontendPort)) {
    $shifted = Get-NextFreePort -Port ($FrontendPort + 1)
    Write-Host "  Frontend port $FrontendPort is taken -> moving to $shifted" -ForegroundColor Yellow
    $FrontendPort = $shifted
}

# The API must allow the frontend origin we actually bound. CORS_ORIGINS is
# explicit (no wildcards), so extend the list from backend\.env with the
# chosen port. The env var takes precedence over the .env file value.
$backendEnv = Join-Path $BackendDir ".env"
$envCors = ""
if (Test-Path $backendEnv) {
    $corsLine = Get-Content $backendEnv | Where-Object { $_ -match '^\s*CORS_ORIGINS\s*=' } | Select-Object -First 1
    if ($corsLine) { $envCors = ($corsLine -split '=', 2)[1].Trim() }
}
$baseCors = @()
if ($envCors) { $baseCors += ($envCors -split '[,;]' | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }
if ($baseCors.Count -eq 0) { $baseCors = @("http://localhost:3000", "http://127.0.0.1:3000") }

function Set-FrontendEnvVars {
    param([int]$Port)
    $corsList = @($baseCors)
    foreach ($origin in @("http://localhost:$Port", "http://127.0.0.1:$Port")) {
        if ($corsList -notcontains $origin) { $corsList += $origin }
    }
    $env:CORS_ORIGINS = ($corsList -join ",")
    # Keep the UI pointed at the API we actually bound (frontend\.env.local
    # holds the default). Next.js only fills in env keys that are not already
    # set, so the inherited value wins over .env.local.
    $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:$ApiPort"
}

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
    # Self-heal: start the Redis systemd service inside WSL2 (password-auth Redis
    # is fine; the backend carries the password in REDIS_URL). Also keeps a
    # detached WSL session alive so the VM (and localhost forwarding) does not
    # idle out while the stack is running.
    Write-Host "Redis preflight: NOT reachable - attempting auto-start via WSL2..." -ForegroundColor Yellow
    try {
        wsl -e bash -lc "sudo -n systemctl start redis-server 2>&1" | Out-Null
        Start-Sleep -Seconds 2
        foreach ($i in 1..5) {
            try {
                $redisProbe = New-Object System.Net.Sockets.TcpClient
                $redisProbe.Connect("127.0.0.1", $RedisPort)
                $redisTest = $redisProbe.Connected
                $redisProbe.Close()
                if ($redisTest) { break }
            } catch { $redisTest = $false }
            Start-Sleep -Seconds 2
        }
    } catch { $redisTest = $false }
    if ($redisTest) {
        # Detached hold-open session: parent PowerShell exits, this survives without dying on stdin EOF.
        Start-Process -FilePath "wsl.exe" -ArgumentList '-d','Ubuntu-26.04','--exec','sleep','infinity' -WindowStyle Hidden | Out-Null
        Write-Host "Redis preflight: auto-started and reachable on 127.0.0.1:$RedisPort" -ForegroundColor Green
    } else {
        Write-Host "Redis preflight: STILL not reachable on 127.0.0.1:$RedisPort (workers/limiter degrade; if Windows->WSL localhost forwarding is down, 'wsl --shutdown' then 'wsl' usually restores it)" -ForegroundColor Yellow
    }
}

$CandidateVenvs = @(
    (Join-Path $BackendDir ".venv"),
    (Join-Path $env:LOCALAPPDATA "mtw-venv")
)
$FoundVenv = $null
foreach ($candidate in $CandidateVenvs) {
    if ((Test-Path (Join-Path $candidate "Scripts\python.exe")) -and (Test-Path (Join-Path $candidate "Scripts\uvicorn.exe"))) {
        $FoundVenv = $candidate
        break
    }
}
if (-not $FoundVenv -and (Test-Path (Join-Path $BackendDir ".venv\Scripts\python.exe"))) {
    $FoundVenv = Join-Path $BackendDir ".venv"
}
if (-not $FoundVenv) {
    Write-Error "Virtual environment not found at $BackendDir\.venv or $env:LOCALAPPDATA\mtw-venv. Please create it first."
    exit 1
}

$PythonExe = Join-Path $FoundVenv "Scripts\python.exe"
$UvicornExe = Join-Path $FoundVenv "Scripts\uvicorn.exe"
$DramatiqExe = Join-Path $FoundVenv "Scripts\dramatiq.exe"

$StartedRoots = @()

# The frontend comes first: another Next.js dev server on this machine can
# auto-increment its port onto ours, so the frontend may still move - and the
# API must be started with the CORS allow-list for the FINAL port.
Write-Host "Starting Frontend on http://localhost:$FrontendPort with Bun..." -ForegroundColor Cyan
$frontendRoot = Start-PersistentProcess -FilePath "bun" -ArgumentList "run dev --port $FrontendPort" -WorkingDirectory $FrontendDir -StdOutPath (Join-Path $LogDir "frontend.log") -StdErrPath (Join-Path $LogDir "frontend_err.log")
$StartedRoots += $frontendRoot
$frontendOk = Wait-Frontend -TimeoutSeconds 45 -RootProcessId $frontendRoot

for ($attempt = 1; ($attempt -le 3) -and (-not $frontendOk); $attempt++) {
    $nextPort = Get-NextFreePort -Port ($FrontendPort + 1)
    Write-Host "  Frontend did not come up on $FrontendPort -> retrying on $nextPort" -ForegroundColor Yellow
    Stop-ProcessTreeById -RootProcessId $frontendRoot
    Start-Sleep -Seconds 2
    $FrontendPort = $nextPort
    $frontendRoot = Start-PersistentProcess -FilePath "bun" -ArgumentList "run dev --port $FrontendPort" -WorkingDirectory $FrontendDir -StdOutPath (Join-Path $LogDir "frontend.log") -StdErrPath (Join-Path $LogDir "frontend_err.log")
    $StartedRoots += $frontendRoot
    $frontendOk = Wait-Frontend -TimeoutSeconds 45 -RootProcessId $frontendRoot
}

Set-FrontendEnvVars -Port $FrontendPort

Write-Host "Starting API on http://127.0.0.1:$ApiPort..." -ForegroundColor Cyan
$StartedRoots += Start-PersistentProcess -FilePath $UvicornExe -ArgumentList "app.main:app --host 127.0.0.1 --port $ApiPort" -WorkingDirectory $BackendDir -StdOutPath (Join-Path $LogDir "api.log") -StdErrPath (Join-Path $LogDir "api_err.log")

Write-Host "Starting HTTP + Notifications Dramatiq Worker..." -ForegroundColor Cyan
$StartedRoots += Start-PersistentProcess -FilePath $DramatiqExe -ArgumentList "app.workers --queues http_checks notifications --processes 1 --threads 2" -WorkingDirectory $BackendDir -StdOutPath (Join-Path $LogDir "worker-http.log") -StdErrPath (Join-Path $LogDir "worker-http_err.log")

Write-Host "Starting Browser Dramatiq Worker..." -ForegroundColor Cyan
$StartedRoots += Start-PersistentProcess -FilePath $DramatiqExe -ArgumentList "app.workers --queues browser_checks --processes 1 --threads 1" -WorkingDirectory $BackendDir -StdOutPath (Join-Path $LogDir "worker-browser.log") -StdErrPath (Join-Path $LogDir "worker-browser_err.log")

Write-Host "Starting Scheduler..." -ForegroundColor Cyan
$StartedRoots += Start-PersistentProcess -FilePath $PythonExe -ArgumentList "-m app.scheduler" -WorkingDirectory $BackendDir -StdOutPath (Join-Path $LogDir "scheduler.log") -StdErrPath (Join-Path $LogDir "scheduler_err.log")

Write-Host ""
Write-Host "=== Stack Status (waiting for services) ===" -ForegroundColor Green
# Honeywell-ish budgets: Neon cold start + DNS blips make first connect slow;
# the API health check earlier failed as a false negative at 3 s.
[void](Wait-ForUrl -Url "http://127.0.0.1:$ApiPort/health" -Label "API Health" -TimeoutSeconds 30 `
        -AliveCheck @{ Name = "uvicorn|python"; Cmd = "app\.main:app"; ErrLog = "api_err.log" })
[void](Wait-ForUrl -Url "http://127.0.0.1:$ApiPort/ready" -Label "DB Ready (Neon)" -TimeoutSeconds 60 `
        -AliveCheck @{ Name = "uvicorn|python"; Cmd = "app\.main:app"; ErrLog = "api_err.log" })

# Record the running tree so the next run can stop it cleanly (including
# Dramatiq's forked workers, whose command line does not name the project).
Save-TrackedProcessIds -RootProcessIds $StartedRoots

Write-Host ""
Write-Host "App URLs:" -ForegroundColor White
Write-Host "  Frontend:  http://localhost:$FrontendPort" -ForegroundColor Cyan
Write-Host "  API Docs:  http://127.0.0.1:$ApiPort/docs" -ForegroundColor Cyan
Write-Host "  Health:    http://127.0.0.1:$ApiPort/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "Logs: data\logs (api, worker-http, worker-browser, scheduler, frontend)" -ForegroundColor DarkGray
Write-Host "Stop:  powershell -File .\scripts\stop-stack.ps1" -ForegroundColor DarkGray
