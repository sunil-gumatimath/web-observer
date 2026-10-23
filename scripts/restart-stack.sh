#!/usr/bin/env bash
# Web Observer Stack Launcher (Linux / WSL2)
# Starts: Frontend (:3000), API (:8002), Dramatiq HTTP worker,
#         Dramatiq browser worker, Scheduler — mirror of restart-stack.ps1
#
# Port handling: a requested port held by another app is never killed; the
# stack moves to the next free port and stays wired up (CORS + API base URL
# follow the ports actually bound). Logs go to data/logs like on Windows.
#
# A detached keepalive session holds the WSL VM open while the stack runs
# (same trick restart-stack.ps1 uses for WSL2 Redis); stop-stack.sh removes it.
set -u

FRONTEND_PORT=3000
API_PORT=8002

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(dirname "$SCRIPT_DIR")
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/data/logs"
PIDS_FILE="$LOG_DIR/our-processes.txt"
KEEPALIVE_FILE="$LOG_DIR/keepalive.pid"
mkdir -p "$LOG_DIR"

FREE_PORT_SHIFT=20

# --- helpers ---------------------------------------------------------------
log()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }

is_running() { kill -0 "$1" 2>/dev/null; }

# Command line of a pid, NUL-separated args joined with spaces.
cmdline_of() {
    if [ -r "/proc/$1/cmdline" ]; then
        tr '\0' ' ' < "/proc/$1/cmdline"
    fi
}

looks_ours() {
    case "$1" in
        *monitor-the-web*|*venvs/monitor-web*) return 0 ;;
        *) return 1 ;;
    esac
}

stop_group() {
    # Kill a process group started via setsid (the whole tree: dramatiq forks,
    # next spawns a worker, uvicorn may reload).
    local pid=$1
    is_running "$pid" || return 0
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        is_running "$pid" || return 0
        sleep 0.5
    done
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
}

port_free() {
    python3 -c "
import socket, sys
s = socket.socket()
s.settimeout(1)
try:
    s.bind(('127.0.0.1', int(sys.argv[1])))
    s.close(); print('free')
except OSError:
    print('busy')
" "$1"
}

next_free_port() {
    local p=$(($1 + 1))
    local top=$(($1 + $FREE_PORT_SHIFT))
    while [ "$p" -le "$top" ]; do
        [ "$(port_free "$p")" = free ] && { echo "$p"; return 0; }
        p=$((p + 1))
    done
    echo "$1"
}

start_root() {
    # start_root <name> <outdir> <workdir> <cmd...> — new session, detached, logged.
    local name=$1 out=$2 dir=$3
    shift 3
    (cd "$dir" && setsid nohup "$@" </dev/null >"$out/$name.log" 2>"$out/$name_err.log" &) 2>/dev/null
    sleep 0.3
}

wait_for_url() {
    # wait_for_url <url> <label> <root_pid> <timeout_s>
    local url=$1 label=$2 root=$3 timeout=$4
    local deadline=$(( $(date +%s) + timeout ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if [ "$root" != 0 ] && ! is_running "$root"; then
            warn "$label : CRASHED - last error lines:"
            tail -n 8 "$LOG_DIR/${label}_err.log" 2>/dev/null | sed 's/^/    /' >&2
            return 1
        fi
        if curl -sf -o /dev/null --max-time 4 "$url"; then
            log "$label : OK"
            return 0
        fi
        sleep 2
    done
    warn "$label : not responding after ${timeout}s (check $LOG_DIR)"
    return 1
}

# --- stop previous run -------------------------------------------------------
log "Stopping any existing Web Observer backend/frontend processes..."
[ -r "$KEEPALIVE_FILE" ] && [ -f "$KEEPALIVE_FILE" ] && stop_group "$(cat "$KEEPALIVE_FILE" 2>/dev/null)"
rm -f "$KEEPALIVE_FILE"

if [ -r "$PIDS_FILE" ]; then
    stopped=0
    while read -r pid; do
        case "$pid" in (*[!0-9]*|'') continue ;; esac
        # A recorded pid may have been reused by an unrelated process; only
        # kill it if it still looks like ours.
        cmd=$(cmdline_of "$pid")
        if [ -n "$cmd" ] && looks_ours "$cmd"; then
            stop_group "$pid"
            stopped=$((stopped + 1))
        fi
    done < "$PIDS_FILE"
    [ "$stopped" -gt 0 ] && log "  Stopped $stopped process group(s) from the previous run"
fi
# Catch stray processes started manually from this repo (mirrors the PS sweep).
for dir in /proc/[0-9]*; do
    pid=${dir#/proc/}
    [ "$pid" = "$$" ] && continue
    cmd=$(cmdline_of "$pid")
    case "$cmd" in
        *restart-stack.sh*) ;;
        *)
            case "$cmd" in
                *"$ROOT_DIR"*) case "$cmd" in
                    *uvicorn*|*dramatiq*|*next*|*scheduler*) is_running "$pid" && stop_group "$pid" ;;
                esac ;;
            esac ;;
    esac
done

# --- port selection -----------------------------------------------------------
[ "$(port_free "$API_PORT")" = busy ] && {
    shifted=$(next_free_port "$API_PORT")
    log "  API port $API_PORT is taken -> moving to $shifted"
    API_PORT=$shifted
}
[ "$(port_free "$FRONTEND_PORT")" = busy ] && {
    shifted=$(next_free_port "$FRONTEND_PORT")
    log "  Frontend port $FRONTEND_PORT is taken -> moving to $shifted"
    FRONTEND_PORT=$shifted
}

# CORS: explicit allow-list from backend/.env, extended with the frontend
# origin actually bound (env var takes precedence over .env values).
CORS_BASE=$(grep -E '^[[:space:]]*CORS_ORIGINS[[:space:]]*=' "$BACKEND_DIR/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r"')
[ -n "$CORS_BASE" ] || CORS_BASE="http://localhost:3000,http://127.0.0.1:3000"
CORS_LIST="$CORS_BASE,http://localhost:$FRONTEND_PORT,http://127.0.0.1:$FRONTEND_PORT"
export CORS_ORIGINS=${CORS_LIST//,,/,}
export NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:$API_PORT"

# --- venv ---------------------------------------------------------------------
VENV=${MTW_VENV:-$HOME/venvs/monitor-web}
PY="$VENV/bin/python"
UVICORN="$VENV/bin/uvicorn"
DRAMATIQ="$VENV/bin/dramatiq"
for binfile in "$PY" "$UVICORN" "$DRAMATIQ"; do
    if [ ! -x "$binfile" ]; then
        warn "Virtual environment not found at $VENV — run the WSL setup steps in docs/local-dev.md first."
        exit 1
    fi
done

# --- keepalive so the WSL VM (and localhost forwarding) stays up ---------------
setsid nohup sleep 2147483647 </dev/null >/dev/null 2>&1 &
KEEPALIVE_PID=$(pgrep -n -f 'sleep 2147483647' 2>/dev/null)
if [ -n "$KEEPALIVE_PID" ] && [ "$KEEPALIVE_PID" != "$$" ]; then
    echo "$KEEPALIVE_PID" > "$KEEPALIVE_FILE"
    log "Keepalive session pid $KEEPALIVE_PID (holds the WSL VM open)"
fi

# --- frontend ------------------------------------------------------------------
log "Starting Frontend on http://localhost:$FRONTEND_PORT ..."
if command -v bun >/dev/null 2>&1; then
    start_root frontend "$LOG_DIR" "$FRONTEND_DIR" bun run dev -- --port "$FRONTEND_PORT"
else
    start_root frontend "$LOG_DIR" "$FRONTEND_DIR" npm run dev -- --port "$FRONTEND_PORT"
fi
FRONTEND_PID=$(pgrep -n -f "next dev.*--port $FRONTEND_PORT" 2>/dev/null || true)
if ! wait_for_url "http://127.0.0.1:$FRONTEND_PORT" frontend "${FRONTEND_PID:-0}" 45; then
    # Retry once on the next free port.
    is_running "${FRONTEND_PID:-0}" && stop_group "$FRONTEND_PID"
    FRONTEND_PORT=$(next_free_port "$FRONTEND_PORT")
    log "  Retrying frontend on port $FRONTEND_PORT"
    export NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:$API_PORT"
    export CORS_ORIGINS="$CORS_BASE,http://localhost:$FRONTEND_PORT,http://127.0.0.1:$FRONTEND_PORT"
    if command -v bun >/dev/null 2>&1; then
        start_root frontend "$LOG_DIR" "$FRONTEND_DIR" bun run dev -- --port "$FRONTEND_PORT"
    else
        start_root frontend "$LOG_DIR" "$FRONTEND_DIR" npm run dev -- --port "$FRONTEND_PORT"
    fi
    FRONTEND_PID=$(pgrep -n -f "next dev.*--port $FRONTEND_PORT" 2>/dev/null || true)
    wait_for_url "http://127.0.0.1:$FRONTEND_PORT" frontend "${FRONTEND_PID:-0}" 45
fi

# --- API + workers + scheduler ---------------------------------------------------
log "Starting API on http://127.0.0.1:$API_PORT ..."
start_root api "$LOG_DIR" "$BACKEND_DIR" "$UVICORN" app.main:app --host 127.0.0.1 --port "$API_PORT"
API_PID=$(pgrep -n -f "app.main:app --host 127.0.0.1 --port $API_PORT")

log "Starting HTTP + notifications Dramatiq worker..."
start_root worker-http "$LOG_DIR" "$BACKEND_DIR" "$DRAMATIQ" app.workers --queues http_checks notifications --processes 1 --threads 2
WORKER_HTTP_PID=$(pgrep -n -f 'dramatiq.*--queues http_checks notifications' | head -1)

log "Starting browser Dramatiq worker (Playwright, --threads 1)..."
start_root worker-browser "$LOG_DIR" "$BACKEND_DIR" "$DRAMATIQ" app.workers --queues browser_checks --processes 1 --threads 1
WORKER_BROWSER_PID=$(pgrep -n -f 'dramatiq.*--queues browser_checks' | head -1)

log "Starting scheduler..."
start_root scheduler "$LOG_DIR" "$BACKEND_DIR" "$PY" -m app.scheduler
SCHED_PID=$(pgrep -n -f '[p]ython -m app.scheduler')

{
    [ -n "$FRONTEND_PID" ] && echo "$FRONTEND_PID"
    [ -n "$API_PID" ] && echo "$API_PID"
    [ -n "$WORKER_HTTP_PID" ] && echo "$WORKER_HTTP_PID"
    [ -n "$WORKER_BROWSER_PID" ] && echo "$WORKER_BROWSER_PID"
    [ -n "$SCHED_PID" ] && echo "$SCHED_PID"
} > "$PIDS_FILE"

# --- health ------------------------------------------------------------------------
log ""
log "=== Stack status (waiting for services) ==="
wait_for_url "http://127.0.0.1:$API_PORT/health" api "$API_PID" 30
wait_for_url "http://127.0.0.1:$API_PORT/ready"  ready "$API_PID" 60

log ""
log "App URLs (also reachable from the Windows browser via WSL localhost forwarding):"
log "  Frontend:  http://localhost:$FRONTEND_PORT"
log "  API Docs:  http://127.0.0.1:$API_PORT/docs"
log "  Health:    http://127.0.0.1:$API_PORT/health"
log ""
log "Logs: data/logs (api, worker-http, worker-browser, scheduler, frontend)"
log "Stop: bash scripts/stop-stack.sh"
