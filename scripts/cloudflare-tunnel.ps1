# Cloudflare Tunnel for Web Observer (free, no static IP, no port-forwarding)
#
# Routes stable public hostnames on your Cloudflare zone to the local stack:
#   app.sunilted.qzz.io -> http://127.0.0.1:3000  (Next.js UI)
#   api.sunilted.qzz.io -> http://127.0.0.1:8002  (FastAPI)
#
# Modes:
#   -Token <tunnel-connector-token>            (dashboard: Zero Trust -> Tunnels ->
#                                              Create tunnel -> copy the token)
#   -Quick                                     (no account needed; random
#                                              trycloudflare.com URL, ephemeral)
#
# The connector token is stored to data/cloudflared-token.txt (gitignored) and
# then cloudflared runs as a Windows service that survives reboots.
#
# NOTE on CORS: the API allow-list (CORS_ORIGINS in backend/.env) must include
# the public UI origin, and the frontend's NEXT_PUBLIC_API_BASE_URL must point
# at the public API origin when the UI is served through the tunnel.
param(
    [string]$TokenFile = (Join-Path $PSScriptRoot "..\data\cloudflared-token.txt"),
    [string]$Token = "",
    [switch]$Quick,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$cloudflared = @(
    (Get-Command cloudflared -ErrorAction SilentlyContinue).Source,
    "$env:ProgramFiles (x86)\cloudflared\cloudflared.exe",
    "$env:ProgramFiles\cloudflared\cloudflared.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if (-not $cloudflared) {
    Write-Host "cloudflared not found. Install it once with:" -ForegroundColor Red
    Write-Host "  winget install Cloudflare.cloudflared" -ForegroundColor Yellow
    exit 1
}
Write-Host "Using cloudflared: $cloudflared"

$ServiceName = "cloudflared"

if ($Remove) {
    & $cloudflared service uninstall 2>$null
    Write-Host "Tunnel service removed."
    exit 0
}

if ($Quick) {
    Write-Host "Quick tunnel (ephemeral trycloudflare.com URL, Ctrl+C to stop):" -ForegroundColor Cyan
    & $cloudflared tunnel --url http://127.0.0.1:3000
    exit 0
}

if (-not $Token) {
    if (Test-Path $TokenFile) {
        $Token = (Get-Content $TokenFile -Raw).Trim()
    }
    if (-not $Token) {
        Write-Host "No connector token. Get it from the dashboard:" -ForegroundColor Red
        Write-Host "  Zero Trust -> Networks -> Tunnels -> Create tunnel -> copy the install token"
        Write-Host "and run:  .\scripts\cloudflare-tunnel.ps1 -Token '<token>'" -ForegroundColor Yellow
        exit 1
    }
}

Set-Content -Path $TokenFile -Value $Token -Encoding ASCII
Write-Host "Connector token saved to $TokenFile (gitignored)."

# Install as a service so the tunnel survives reboots and stack restarts.
& $cloudflared service install $Token
Start-Service $ServiceName -ErrorAction SilentlyContinue
Get-Service $ServiceName | Select-Object Status, Name, DisplayName
Write-Host ""
Write-Host "Tunnel service is running. Hostnames configured in the dashboard"
Write-Host "(app.sunilted.qzz.io -> 127.0.0.1:3000, api.sunilted.qzz.io -> 127.0.0.1:8002)"
Write-Host "are now live while this PC is on." -ForegroundColor Green
