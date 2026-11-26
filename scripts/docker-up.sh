#!/usr/bin/env bash
# Thin wrapper around `docker compose` for the Web Observer stack.
#
# It exists for one reason: NEXT_PUBLIC_* variables are inlined into the
# Next.js bundle at build time, so they must be present in the build
# environment — not just in the container at runtime. This script exports the
# values from frontend/.env.local before calling compose.
#
# Usage:
#   ./scripts/docker-up.sh                 # build + start (detached)
#   ./scripts/docker-up.sh up --build      # same, explicit
#   ./scripts/docker-up.sh down            # stop
#   ./scripts/docker-up.sh logs -f api     # follow a service
#   ./scripts/docker-up.sh ps
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

# --- Docker socket access ----------------------------------------------------
# In WSL the `docker` group is often present in /etc/group but missing from the
# current login session's group list, which surfaces as "permission denied" on
# /var/run/docker.sock. Re-run ourselves under `sg docker` instead of asking the
# user to open a new shell.
if ! docker info >/dev/null 2>&1; then
    if command -v sg >/dev/null 2>&1 && grep -qE "^docker:.*\b${USER}\b" /etc/group; then
        echo "docker socket not accessible to this shell; re-running with the docker group..." >&2
        exec sg docker -c "$(printf '%q ' "$0" "$@")"
    fi
    echo "error: cannot talk to the Docker daemon. Is Docker Desktop running?" >&2
    exit 1
fi

# --- Build-time public variables --------------------------------------------
# Parsed rather than sourced: the file may have CRLF line endings (it lives on
# a Windows mount), which bash cannot source.
if [[ -f frontend/.env.local ]]; then
    while IFS='=' read -r key value || [[ -n $key ]]; do
        [[ $key =~ ^NEXT_PUBLIC_[A-Za-z0-9_]+$ ]] || continue
        [[ $key == "NEXT_PUBLIC_INTERNAL_API_TOKEN" ]] && continue
        value=${value%$'\r'}
        value=${value#\"}
        value=${value%\"}
        export "$key=$value"
    done < frontend/.env.local
fi

if [[ $# -eq 0 ]]; then
    set -- up -d --build
fi

exec docker compose "$@"
