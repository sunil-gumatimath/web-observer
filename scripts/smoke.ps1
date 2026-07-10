# Phase 1 smoke test against a running API (docker compose up).
# Usage: powershell -File scripts/smoke.ps1

$ErrorActionPreference = "Stop"
$Base = if ($env:API_BASE) { $env:API_BASE } else { "http://localhost:8000" }
$Token = if ($env:INTERNAL_API_TOKEN) { $env:INTERNAL_API_TOKEN } else { "dev-internal-token" }
$Headers = @{ "X-Internal-Token" = $Token; "Content-Type" = "application/json" }

Write-Host "== health =="
$health = Invoke-RestMethod -Uri "$Base/health" -Method Get
Write-Host ($health | ConvertTo-Json -Compress)

Write-Host "== seed =="
$seed = Invoke-RestMethod -Uri "$Base/api/v1/internal/seed" -Method Post -Headers $Headers
$ws = $seed.workspace_id
Write-Host "workspace_id=$ws"

Write-Host "== create monitor =="
$body = @{
    name = "Smoke example.com"
    url = "https://example.com/"
    mode = "whole_page"
    schedule_interval_minutes = 60
    notification_email = "smoke@example.com"
} | ConvertTo-Json
$mon = Invoke-RestMethod -Uri "$Base/api/v1/workspaces/$ws/monitors" -Method Post -Headers $Headers -Body $body
$mid = $mon.id
Write-Host "monitor_id=$mid"

Write-Host "== manual run =="
$run = Invoke-RestMethod -Uri "$Base/api/v1/workspaces/$ws/monitors/$mid/run" -Method Post -Headers $Headers
Write-Host "run_id=$($run.run_id) status=$($run.status)"

Write-Host "== wait for completion =="
$final = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    $runs = Invoke-RestMethod -Uri "$Base/api/v1/workspaces/$ws/monitors/$mid/runs" -Method Get -Headers $Headers
    if ($runs.Count -gt 0) {
        $final = $runs[0]
        if ($final.status -in @("succeeded", "failed", "cancelled")) { break }
    }
}

if (-not $final) {
    Write-Error "No run found"
    exit 1
}

Write-Host ("run status={0} http={1} error={2}" -f $final.status, $final.http_status, $final.error_code)

Write-Host "== usage =="
$usage = Invoke-RestMethod -Uri "$Base/api/v1/workspaces/$ws/usage" -Method Get -Headers $Headers
Write-Host ($usage | ConvertTo-Json -Compress)

if ($final.status -ne "succeeded") {
    Write-Error "Smoke failed: run status=$($final.status) code=$($final.error_code) msg=$($final.error_message)"
    exit 1
}

Write-Host "SMOKE OK"
exit 0
