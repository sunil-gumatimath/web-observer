# Kill app ports and restart Web Observer local stack (Windows).
# Usage:  powershell -File .\scripts\restart-stack.ps1

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$LogDir = Join-Path $Root "data\logs"
$RunDir = Join-Path $LogDir "run"
$ApiPort = 8002
$FePort = 3000

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

function Stop-PortListeners([int[]]$Ports) {
    foreach ($port in $Ports) {
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
            $procId = $_.OwningProcess
            if ($procId -and $procId -gt 0 -and $procId -ne $PID) {
                $name = (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName
                Write-Host "  stop port $port PID $procId ($name)"
                taskkill /F /T /PID $procId 2>$null | Out-Null
            }
        }
    }
}

function Stop-ProjectProcesses {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'node.exe'" | ForEach-Object {
        $cmd = $_.CommandLine
        if (-not $cmd) { return }
        $ours = $cmd -like "*monitor-the-web*"
        $role = (
            $cmd -like "*uvicorn*" -or
            $cmd -like "*dramatiq*" -or
            $cmd -like "*app.scheduler*" -or
            $cmd -like "*next*dev*" -or
            ($cmd -like "*node*" -and $cmd -like "*frontend*")
        )
        if ($ours -and $role -and $_.ProcessId -ne $PID) {
            Write-Host "  stop $($_.Name) PID $($_.ProcessId)"
            taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null
        }
    }
}

function Write-BackendEnvBlock {
    $sb = New-Object System.Text.StringBuilder
    $envFile = Join-Path $Backend ".env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            $line = $_.Trim()
            if (-not $line -or $line.StartsWith("#")) { return }
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
                $k = $Matches[1]
                $v = $Matches[2].Trim().Trim("'").Trim('"') -replace "'", "''"
                [void]$sb.AppendLine("`$env:$k = '$v'")
            }
        }
    }
    $snap = Join-Path $Root "data\snapshots"
    [void]$sb.AppendLine("`$env:LOCAL_STORAGE_PATH = '$snap'")
    return $sb.ToString()
}

function Start-ServiceWindow {
    param(
        [string]$Title,
        [string]$WorkDir,
        [string]$LineToRun,
        [string]$LogName,
        [switch]$WithBackendEnv
    )

    $log = Join-Path $LogDir $LogName
    $runner = Join-Path $RunDir ("start-" + ($Title -replace '[^a-zA-Z0-9\-]', '_') + ".ps1")
    [System.IO.File]::WriteAllText($log, "=== $Title starting $(Get-Date -Format o) ===`r`n")

    $envBlock = ""
    if ($WithBackendEnv) { $envBlock = Write-BackendEnvBlock }

    $script = @"
`$ErrorActionPreference = 'Continue'
$envBlock
Set-Location -LiteralPath '$WorkDir'
`$Host.UI.RawUI.WindowTitle = '$Title'
Write-Host '=== $Title ===' -ForegroundColor Cyan
Write-Host 'Log: $log'
Write-Host 'Cmd: $LineToRun'
Write-Host ''
try {
    Invoke-Expression '$LineToRun' *>> '$log'
} catch {
    `$_ | Out-String | Add-Content -LiteralPath '$log'
    Write-Host `$_ -ForegroundColor Red
}
Write-Host ''
Write-Host 'Process exited. Window stays open so you can read errors.' -ForegroundColor Yellow
Write-Host 'Press Enter to close...'
[void](Read-Host)
"@
    # Fix: LineToRun may contain single quotes - escape for the outer single-quoted Invoke-Expression
    # Better: don't use Invoke-Expression with single quotes; embed command directly.
    $script = @"
`$ErrorActionPreference = 'Continue'
$envBlock
Set-Location -LiteralPath '$WorkDir'
`$Host.UI.RawUI.WindowTitle = '$Title'
Write-Host '=== $Title ===' -ForegroundColor Cyan
Write-Host 'Log: $log'
Write-Host ''
try {
    $LineToRun *>> '$log'
} catch {
    `$_ | Out-String | Add-Content -LiteralPath '$log'
    Write-Host `$_ -ForegroundColor Red
}
Write-Host ''
Write-Host 'Process exited. Window stays open so you can read errors.' -ForegroundColor Yellow
Write-Host 'Press Enter to close...'
[void](Read-Host)
"@
    Set-Content -LiteralPath $runner -Value $script -Encoding UTF8

    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $runner
    ) | Out-Null
    Write-Host "  launched $Title"
}

function Wait-HttpOk([string]$Url, [int]$Seconds = 90) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) {
                return $true
            }
        } catch { }
        Start-Sleep -Seconds 1
    }
    return $false
}

Write-Host "=== Stopping old processes ===" -ForegroundColor Yellow
Stop-PortListeners -Ports @($FePort, $ApiPort, 8000, 8001)
Stop-ProjectProcesses
Start-Sleep -Seconds 2

Write-Host "=== Starting services ===" -ForegroundColor Green
$uv = Join-Path $Backend ".venv\Scripts\uvicorn.exe"
$dm = Join-Path $Backend ".venv\Scripts\dramatiq.exe"
$py = Join-Path $Backend ".venv\Scripts\python.exe"

if (-not (Test-Path $uv)) {
    Write-Host "Missing venv at $Backend\.venv" -ForegroundColor Red
    exit 1
}

Start-ServiceWindow -Title "WO-API" -WorkDir $Backend -WithBackendEnv -LogName "api.log" `
    -LineToRun "& '$uv' app.main:app --host 127.0.0.1 --port $ApiPort"
Start-Sleep -Seconds 2

Start-ServiceWindow -Title "WO-Worker-HTTP" -WorkDir $Backend -WithBackendEnv -LogName "worker-http.log" `
    -LineToRun "& '$dm' app.workers --queues http_checks notifications --processes 1 --threads 2"

Start-ServiceWindow -Title "WO-Worker-Browser" -WorkDir $Backend -WithBackendEnv -LogName "worker-browser.log" `
    -LineToRun "& '$dm' app.workers --queues browser_checks --processes 1 --threads 1"

Start-ServiceWindow -Title "WO-Scheduler" -WorkDir $Backend -WithBackendEnv -LogName "scheduler.log" `
    -LineToRun "& '$py' -m app.scheduler"

Start-ServiceWindow -Title "WO-Frontend" -WorkDir $Frontend -LogName "frontend.log" `
    -LineToRun "npm run dev -- --port $FePort"

Write-Host "=== Waiting for health ===" -ForegroundColor Cyan
$apiOk = Wait-HttpOk "http://127.0.0.1:$ApiPort/health" 90
$feOk = Wait-HttpOk "http://127.0.0.1:$FePort/" 90

if ($apiOk) {
    Write-Host "API OK  http://127.0.0.1:$ApiPort/health" -ForegroundColor Green
} else {
    Write-Host "API FAILED - see data\logs\api.log and WO-API window" -ForegroundColor Red
    Get-Content (Join-Path $LogDir "api.log") -Tail 25 -ErrorAction SilentlyContinue
}

if ($feOk) {
    Write-Host "Frontend OK  http://127.0.0.1:$FePort/" -ForegroundColor Green
} else {
    Write-Host "Frontend FAILED - see data\logs\frontend.log and WO-Frontend window" -ForegroundColor Red
    Get-Content (Join-Path $LogDir "frontend.log") -Tail 30 -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Open:  http://127.0.0.1:$FePort" -ForegroundColor Cyan
Write-Host "API:   http://127.0.0.1:$ApiPort/docs"
Write-Host "Leave the WO-* PowerShell windows open."

if ($apiOk -and $feOk) { exit 0 } else { exit 1 }
