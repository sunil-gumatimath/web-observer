#!/usr/bin/env bash
# Web Observer backend stack inside WSL2 (native Redis on 127.0.0.1:6379).
# Runs the FastAPI API, both Dramatiq workers and the scheduler as
# systemd transient units. Project is NOT copied: it is used in place
# via the /mnt/c mount of the Windows working copy.
#
# Usage (from Windows):  wsl -e bash /mnt/c/Users/Tedz/OneDrive/Desktop/Projects/monitor-the-web/scripts/run-wsl-stack.sh
set -euo pipefail

ROOT="/mnt/c/Users/Tedz/OneDrive/Desktop/Projects/monitor-the-web"
BACKEND="$ROOT/backend"
VENV="$HOME/venvs/monitor-web"
LOG="$ROOT/data/logs"

mkdir -p "$LOG"

# Logs may exist root-owned from previous (root) unit runs; make them writable.
sudo -n chown -R ted:ted "$LOG" 2>/dev/null || true
# Stray test frontend from manual debugging
pkill -f 'next dev --port 3001' 2>/dev/null || true

# --- Redis must be listening (systemd-managed redis-server) -------------------
redis_ab=`systemctl is-active redis-server 2>/dev/null` || true
redis_up=`ss -tln | grep -q ':6379 ' && echo yes || echo no`
if [[ "$redis_ab" != active || "$redis_up" != yes ]]; then
    echo "Redis is not listening on 127.0.0.1:6379 -> starting redis-server..."
    sudo -n systemctl start redis-server
    sleep 1
fi

# --- (Re)start the four backend units -----------------------------------------
for unit in mtw-api mtw-worker-http mtw-worker-browser mtw-scheduler; do
    sudo -n systemctl stop "$unit" 2>/dev/null || true
    sudo -n systemctl reset-failed "$unit" 2>/dev/null || true
done

sudo -n systemd-run -u mtw-api \
    -p User=ted -p Group=ted \
    -p WorkingDirectory="$BACKEND" \
    -p StandardOutput=file:"$LOG/wsl-api.log" \
    -p StandardError=file:"$LOG/wsl-api_err.log" \
    "$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8002

sudo -n systemd-run -u mtw-worker-http \
    -p User=ted -p Group=ted \
    -p WorkingDirectory="$BACKEND" \
    -p StandardOutput=file:"$LOG/wsl-worker-http.log" \
    -p StandardError=file:"$LOG/wsl-worker-http_err.log" \
    "$VENV/bin/dramatiq" app.workers --queues http_checks notifications --processes 1 --threads 2

sudo -n systemd-run -u mtw-worker-browser \
    -p User=ted -p Group=ted \
    -p WorkingDirectory="$BACKEND" \
    -p StandardOutput=file:"$LOG/wsl-worker-browser.log" \
    -p StandardError=file:"$LOG/wsl-worker-browser_err.log" \
    "$VENV/bin/dramatiq" app.workers --queues browser_checks --processes 1 --threads 1

sudo -n systemd-run -u mtw-scheduler \
    -p User=ted -p Group=ted \
    -p WorkingDirectory="$BACKEND" \
    -p StandardOutput=file:"$LOG/wsl-scheduler.log" \
    -p StandardError=file:"$LOG/wsl-scheduler_err.log" \
    "$VENV/bin/python" -m app.scheduler

if [[ -L "$ROOT/frontend/.next" ]]; then
    sudo -n rm "$ROOT/frontend/.next"
    mkdir -p "$ROOT/frontend/.next"
fi
sudo -n systemd-run -u mtw-frontend \
    -p User=ted -p Group=ted \
    -p WorkingDirectory="$ROOT/frontend" \
    -p StandardOutput=file:"$LOG/wsl-frontend.log" \
    -p StandardError=file:"$LOG/wsl-frontend_err.log" \
    /usr/bin/node "$HOME/mtw-web/node_modules/next/dist/bin/next" dev --port 3000 --webpack --hostname 0.0.0.0

sleep 6
echo "--- unit states ---"
systemctl is-active mtw-api mtw-worker-http mtw-worker-browser mtw-scheduler mtw-frontend || true
echo "--- API health ---"
curl -s -m 5 http://127.0.0.1:8002/health && echo " <- OK"
