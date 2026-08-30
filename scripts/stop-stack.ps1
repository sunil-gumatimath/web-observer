# Web Observer Stack Stopper
$ErrorActionPreference = 'SilentlyContinue'

Write-Host "Stopping Web Observer backend and frontend processes..." -ForegroundColor Yellow

# Kill via WMI/CIM matching command line or path
Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -match "python|dramatiq|uvicorn|bun|node") -and 
    ($_.CommandLine -match "monitor-the-web|uvicorn|dramatiq|app\.scheduler|next dev|WO-")
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
}

# Free ports 8002 and 3000
try {
    $ports = @(8002, 3000)
    foreach ($port in $ports) {
        $pidsToKill = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($p in $pidsToKill) {
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        }
    }
} catch {
    # Ignore if NetTCPIP cmdlet is unavailable
}

Write-Host "All Web Observer services stopped." -ForegroundColor Green
