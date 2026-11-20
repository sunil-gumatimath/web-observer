#!/usr/bin/env bash
# Container entrypoint: make sure the Redis data volume is writable, then hand
# over to supervisord, which owns every process in the stack.
set -euo pipefail

mkdir -p /data

exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
