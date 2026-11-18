#!/usr/bin/env bash
# Install persistent systemd unit files for the Web Observer stack inside WSL2.
# Units start on WSL boot (systemd) and are NOT transient, so they survive the
# closing of the wsl.exe session that installed them. The repo root, runtime
# user/group and venv are derived here — nothing is tied to one machine's path.
#
# Usage (from Windows):  wsl -e bash <repo>/scripts/install-wsl-units.sh
# Usage (from the repo): bash scripts/install-wsl-units.sh
#
# Assumptions (override where noted): WSL2 distro with systemd and passwordless
# sudo (`sudo -n`), a systemd `redis-server` service, a repo-local backend/.venv
# with requirements installed, and installed frontend dependencies. Override the
# venv with MTW_VENV, the unit user/group with MTW_RUN_USER/MTW_RUN_GROUP, the
# node/next binaries with MTW_NODE_BIN/MTW_NEXT_BIN.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(dirname "$SCRIPT_DIR")
LOG="$ROOT/data/logs"
VENV=${MTW_VENV:-$ROOT/backend/.venv}
RUN_USER=${MTW_RUN_USER:-${USER:-$(id -un)}}
RUN_GROUP=${MTW_RUN_GROUP:-$(id -gn)}
NODE_BIN=${MTW_NODE_BIN:-$(command -v node || echo /usr/bin/node)}
NEXT_BIN=${MTW_NEXT_BIN:-$ROOT/frontend/node_modules/next/dist/bin/next}

mkdir -p "$LOG"

unit() {
    name=$1
    desc=$2
    exec=$3
    sudo -n tee "/etc/systemd/system/${name}.service" >/dev/null <<EOF
[Unit]
Description=$desc (Web Observer)
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$4
ExecStart=$exec
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
}

unit mtw-api "FastAPI backend" \
    "$VENV/bin/uvicorn app.main:app --host 0.0.0.0 --port 8002" \
    "$ROOT/backend"

unit mtw-worker-http "Dramatiq HTTP + notifications worker" \
    "$VENV/bin/dramatiq app.workers --queues http_checks notifications --processes 1 --threads 2" \
    "$ROOT/backend"

unit mtw-worker-browser "Dramatiq browser worker (Playwright)" \
    "$VENV/bin/dramatiq app.workers --queues browser_checks --processes 1 --threads 1" \
    "$ROOT/backend"

unit mtw-scheduler "Due-monitor scheduler" \
    "$VENV/bin/python -m app.scheduler" \
    "$ROOT/backend"

# Frontend: webpack dev stays for compatibility with node_modules symlinked
# across filesystems (Turbopack rejects that). By default use the repo-local
# frontend/node_modules; set MTW_NEXT_BIN if yours lives elsewhere.
FRONT="$ROOT/frontend"
if [[ -L "$FRONT/.next" ]]; then sudo -n rm "$FRONT/.next"; fi
mkdir -p "$FRONT/.next"
sudo -n tee /etc/systemd/system/mtw-frontend.service >/dev/null <<EOF
[Unit]
Description=Next.js frontend (Web Observer)
After=network.target mtw-api.service

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$FRONT
ExecStart=$NODE_BIN $NEXT_BIN dev --port 3000 --webpack --hostname 0.0.0.0
Environment=NODE_ENV=development
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo -n systemctl daemon-reload
sudo -n systemctl enable mtw-api mtw-worker-http mtw-worker-browser mtw-scheduler mtw-frontend 2>&1 | grep -v '^$' || true
sudo -n systemctl restart mtw-api mtw-worker-http mtw-worker-browser mtw-scheduler mtw-frontend
sleep 8
echo "--- unit states ---"
systemctl is-active mtw-api mtw-worker-http mtw-worker-browser mtw-scheduler mtw-frontend
echo "--- API health ---"
curl -s -m 5 http://127.0.0.1:8002/health && echo " <- OK"
