#!/usr/bin/env bash
# Block until the bundled Redis answers PING, then exec the real command.
# Supervisor starts processes by priority, but a restart can still race the
# Redis restart, so every Redis consumer goes through this gate.
set -euo pipefail

for _ in $(seq 1 120); do
    if redis-cli -h 127.0.0.1 -p 6379 ping >/dev/null 2>&1; then
        exec "$@"
    fi
    sleep 0.5
done

echo "wait-for-redis: redis did not become ready within 60s" >&2
exit 1
