#!/usr/bin/env bash
# Web Observer backend stack inside WSL2 (native Redis on 127.0.0.1:6379).
# Runs the FastAPI API, both Dramatiq workers and the scheduler as
# systemd transient units. Project is NOT copied: it is used in place from
# wherever this script lives (a WSL mount or a native checkout). The repo root
# is derived from the script location, and the runtime user/group come from the
# invoking shell; nothing is tied to one machine's username or path.
#
# Usage (from Windows):  wsl -e bash <repo>/scripts/run-wsl-stack.sh
# Usage (from the repo): bash scripts/run-wsl-stack.sh
#
# Assumptions (override where noted): WSL2 distro with systemd and passwordless
# sudo (`sudo -n`), a systemd `redis-server` service, a repo-local backend/.venv
# with requirements installed, and installed frontend dependencies. Override the
# venv with MTW_VENV, the unit user/group with MTW_RUN_USER/MTW_RUN_GROUP, the
# node/next binaries with MTW_NODE_BIN/MTW_NEXT_BIN.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(dirname "$SCRIPT_DIR")
BACKEND="$ROOT/backend"
VENV=${MTW_VENV:-$BACKEND/.venv}
LOG="$ROOT/data/logs"
RUN_USER=${MTW_RUN_USER:-${USER:-$(id -un)}}
RUN_GROUP=${MTW_RUN_GROUP:-$(id -gn)}
NODE_BIN=${MTW_NODE_BIN:-$(command -v node || echo /usr/bin/node)}
NEXT_BIN=${MTW_NEXT_BIN:-$ROOT/frontend/node_modules/next/dist/bin/next}

mkdir -p "$LOG"

# Logs may exist root-owned from previous (root) unit runs; make them writable.
sudo -n chown -R "$RUN_USER:$RUN_GROUP" "$LOG" 2>/dev/null || true
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
    -p User="$RUN_USER" -p Group="$RUN_GROUP" \
    -p WorkingDirectory="$BACKEND" \
    -p StandardOutput=file:"$LOG/wsl-api.log" \
    -p StandardError=file:"$LOG/wsl-api_err.log" \
    "$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8002

sudo -n systemd-run -u mtw-worker-http \
    -p User="$RUN_USER" -p Group="$RUN_GROUP" \
    -p WorkingDirectory="$BACKEND" \
    -p StandardOutput=file:"$LOG/wsl-worker-http.log" \
    -p StandardError=file:"$LOG/wsl-worker-http_err.log" \
    "$VENV/bin/dramatiq" app.workers --queues http_checks notifications --processes 1 --threads 2

sudo -n systemd-run -u mtw-worker-browser \
    -p User="$RUN_USER" -p Group="$RUN_GROUP" \
    -p WorkingDirectory="$BACKEND" \
    -p StandardOutput=file:"$LOG/wsl-worker-browser.log" \
    -p StandardError=file:"$LOG/wsl-worker-browser_err.log" \
    "$VENV/bin/dramatiq" app.workers --queues browser_checks --processes 1 --threads 1

sudo -n systemd-run -u mtw-scheduler \
    -p User="$RUN_USER" -p Group="$RUN_GROUP" \
    -p WorkingDirectory="$BACKEND" \
    -p StandardOutput=file:"$LOG/wsl-scheduler.log" \
    -p StandardError=file:"$LOG/wsl-scheduler_err.log" \
    "$VENV/bin/python" -m app.scheduler

if [[ -L "$ROOT/frontend/.next" ]]; then
    sudo -n rm "$ROOT/frontend/.next"
    mkdir -p "$ROOT/frontend/.next"
fi
sudo -n systemd-run -u mtw-frontend \
    -p User="$RUN_USER" -p Group="$RUN_GROUP" \
    -p WorkingDirectory="$ROOT/frontend" \
    -p StandardOutput=file:"$LOG/wsl-frontend.log" \
    -p StandardError=file:"$LOG/wsl-frontend_err.log" \
    # --webpack stays for compatibility when node_modules is symlinked across
    # filesystems (Turbopack rejects that); set MTW_NEXT_BIN if it lives elsewhere.
    "$NODE_BIN" "$NEXT_BIN" dev --port 3000 --webpack --hostname 0.0.0.0

sleep 6
echo "--- unit states ---"
systemctl is-active mtw-api mtw-worker-http mtw-worker-browser mtw-scheduler mtw-frontend || true
echo "--- API health ---"
curl -s -m 5 http://127.0.0.1:8002/health && echo " <- OK"
