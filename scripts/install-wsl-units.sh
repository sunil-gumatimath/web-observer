#!/usr/bin/env bash
# Install persistent systemd unit files for the Web Observer stack inside WSL2.
# Units start on WSL boot (systemd) and are NOT transient, so they survive the
# closing of the wsl.exe session that installed them.
#   Project is used in place at /mnt/c (nothing is copied into WSL).
# Usage: wsl -e bash /mnt/c/Users/Tedz/OneDrive/Desktop/Projects/monitor-the-web/scripts/install-wsl-units.sh
set -euo pipefail

ROOT="/mnt/c/Users/Tedz/OneDrive/Desktop/Projects/monitor-the-web"
LOG="$ROOT/data/logs"
VENV="$HOME/venvs/monitor-web"

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
User=ted
Group=ted
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

# Frontend: webpack dev (Turbopack rejects node_modules symlinked to the ext4
# home); node_modules is symlinked from ~/mtw-web so it lives on Linux disk.
FRONT="$ROOT/frontend"
NGENTO="$HOME/mtw-web/node_modules"
if [[ -L "$FRONT/.next" ]]; then sudo -n rm "$FRONT/.next"; fi
mkdir -p "$FRONT/.next"
sudo -n tee /etc/systemd/system/mtw-frontend.service >/dev/null <<EOF
[Unit]
Description=Next.js frontend (Web Observer)
After=network.target mtw-api.service

[Service]
Type=simple
User=ted
Group=ted
WorkingDirectory=$FRONT
ExecStart=/usr/bin/node $NGENTO/next/dist/bin/next dev --port 3000 --webpack --hostname 0.0.0.0
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
