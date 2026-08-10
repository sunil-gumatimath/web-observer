#!/usr/bin/env bash
# Starts the backend stack (API + Dramatiq workers + scheduler) in the background.
# Logs go to logs/<service>.log, PIDs to logs/<service>.pid.
# Frontend (npm run dev) and Redis are expected to run separately.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
cd backend

VENV="$ROOT/backend/.venv/Scripts"
PY="$VENV/python.exe"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

# Kill existing stack if running
for svc in api worker-http worker-browser scheduler; do
  if [ -f "$LOG_DIR/$svc.pid" ]; then
    pid=$(cat "$LOG_DIR/$svc.pid" 2>/dev/null || true)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "stopping $svc (pid $pid)"
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$LOG_DIR/$svc.pid"
  fi
done
sleep 1

start() {
  local svc="$1"; shift
  nohup "$@" > "$LOG_DIR/$svc.log" 2>&1 &
  echo $! > "$LOG_DIR/$svc.pid"
  echo "started $svc (pid $!) -> logs/$svc.log"
}

start api "$VENV/uvicorn.exe" app.main:app --host 127.0.0.1 --port 8002
start worker-http "$VENV/dramatiq.exe" app.workers --queues http_checks notifications --processes 1 --threads 2
start worker-browser "$VENV/dramatiq.exe" app.workers --queues browser_checks --processes 1 --threads 1
start scheduler "$PY" -m app.scheduler

echo "---"
echo "All services launching. URLs:"
echo "  API     http://127.0.0.1:8002/health"
echo "  Docs    http://127.0.0.1:8002/docs"
echo "  Frontend http://127.0.0.1:3000"
