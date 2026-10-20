# Web Observer Stack Stopper
#
# Stops only the processes this stack started:
#   - the PIDs recorded by restart-stack.ps1 (data\logs\our-processes.txt),
#     plus anything orphaned by a dead parent (Dramatiq's forked workers);
#   - any process running from this repository.
#
# It deliberately does NOT free ports by killing whoever happens to listen on
# them: another app may own port 3000 (or any other port) legitimately.
$ErrorActionPreference = 'SilentlyContinue'

$RootDir = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $RootDir "data\logs"
$StateFile = Join-Path $LogDir "our-processes.txt"

Write-Host "Stopping Web Observer backend and frontend processes..." -ForegroundColor Yellow

$tracked = @()
if (Test-Path $StateFile) {
    foreach ($line in (Get-Content $StateFile -ErrorAction SilentlyContinue)) {
        $t = $line.Trim()
        if ($t -match '^\d+$') { $tracked += [int]$t }
    }
}

$snapshot = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)

# Never kill this script or its ancestors.
$protect = @()
$current = $PID
while ($current -gt 0) {
    $protect += $current
    $proc = $snapshot | Where-Object { $_.ProcessId -eq $current } | Select-Object -First 1
    if (-not $proc) { break }
    $current = [int]$proc.ParentProcessId
}

$victims = @()
foreach ($p in $snapshot) {
    if ($protect -contains $p.ProcessId) { continue }
    if ($tracked -contains $p.ProcessId) {
        # A recorded PID may have been reused by an unrelated process since it
        # was recorded - only kill it if it still looks like ours.
        $looksOurs = ($p.CommandLine -match "monitor-the-web") -or ($tracked -contains $p.ParentProcessId)
        if ($looksOurs) { $victims += $p.ProcessId }
        continue
    }
    # Orphaned worker whose parent was recorded but has since died.
    if ($tracked -contains $p.ParentProcessId) { $victims += $p.ProcessId }
}

# Anything started by hand from this repository.
foreach ($p in $snapshot) {
    if ($p.Name -notmatch "python|dramatiq|uvicorn|bun|node|cmd") { continue }
    if ($p.CommandLine -notmatch "monitor-the-web") { continue }
    if ($p.CommandLine -match "stop-stack\.ps1|restart-stack\.ps1") { continue }
    if ($protect -contains $p.ProcessId) { continue }
    $victims += $p.ProcessId
}

$stopped = 0
foreach ($id in ($victims | Select-Object -Unique)) {
    if ($snapshot | Where-Object { $_.ProcessId -eq $id }) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        $stopped++
    }
}

if (Test-Path $StateFile) { Remove-Item $StateFile -Force -ErrorAction SilentlyContinue }

Write-Host "All Web Observer services stopped ($stopped process(es))." -ForegroundColor Green
