#!/usr/bin/env bash
# Web Observer Stack Stopper (Linux / WSL2) — mirror of stop-stack.ps1.
# Stops only processes this stack started (tracked in data/logs/our-processes.txt,
# verified via /proc cmdlines, plus strays started from this repo) and the
# keepalive session that holds the WSL VM open.
set -u

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(dirname "$SCRIPT_DIR")
LOG_DIR="$ROOT_DIR/data/logs"
PIDS_FILE="$LOG_DIR/our-processes.txt"
KEEPALIVE_FILE="$LOG_DIR/keepalive.pid"

is_running() { kill -0 "$1" 2>/dev/null; }
cmdline_of() { tr '\0' ' ' < "/proc/$1/cmdline" 2>/dev/null; }
looks_ours() {
    case "$1" in *monitor-the-web*|*venvs/monitor-web*) return 0 ;; *) return 1 ;; esac
}
stop_group() {
    local pid=$1
    is_running "$pid" || return 0
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        is_running "$pid" || return 0
        sleep 0.5
    done
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
}

count=0

# Keepalive session first so the VM can idle out after the stack stops.
if [ -r "$KEEPALIVE_FILE" ]; then
    kp=$(cat "$KEEPALIVE_FILE" 2>/dev/null)
    if [ -n "$kp" ] && is_running "$kp"; then
        stop_group "$kp"
        count=$((count + 1))
    fi
    rm -f "$KEEPALIVE_FILE"
fi

# Tracked processes (pid reuse guard: only kill pids that still look ours).
if [ -r "$PIDS_FILE" ]; then
    while read -r pid; do
        case "$pid" in (*[!0-9]*|'') continue ;; esac
        cmd=$(cmdline_of "$pid")
        if [ -n "$cmd" ] && looks_ours "$cmd"; then
            stop_group "$pid"
            count=$((count + 1))
        fi
    done < "$PIDS_FILE"
    : > "$PIDS_FILE"
fi

# Strays started manually from this repo (path check keeps foreign apps safe).
for dir in /proc/[0-9]*; do
    pid=${dir#/proc/}
    [ "$pid" = "$$" ] && continue
    cmd=$(cmdline_of "$pid")
    [ -n "$cmd" ] || continue
    looks_ours "$cmd" || continue
    case "$cmd" in
        *restart-stack.sh*|*stop-stack.sh*) continue ;;
        *uvicorn*|*dramatiq*|*next*|*"app.scheduler"*)
            if is_running "$pid"; then
                stop_group "$pid"
                count=$((count + 1))
            fi ;;
    esac
done

echo "Stopped $count process group(s)."
