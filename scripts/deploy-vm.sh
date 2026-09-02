#!/usr/bin/env bash
# Web Observer — Google Cloud Free VM Deployment Script
# Configures swap, dependencies, python virtualenv, Playwright, and systemd services.
set -euo pipefail

echo "==> Step 1: Checking and configuring Swap (required for 1GB RAM VM)..."
if [ ! -f /swapfile ]; then
  sudo fallocate -l 4G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=4096
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  echo "Swap configured: 4GB"
else
  echo "Swapfile already exists."
fi

echo "==> Step 2: Installing system packages and Redis..."
sudo apt-get update
sudo apt-get install -y \
  curl git redis-server \
  python3 python3-pip python3-venv \
  libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
  libgbm1 libpango-1.0-0 libpangocairo-1.0-0

sudo systemctl enable --now redis-server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "==> Step 3: Setting up Python virtual environment in $BACKEND_DIR..."
cd "$BACKEND_DIR"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Step 4: Installing Playwright Chromium browser..."
python3 -m playwright install --with-deps chromium

echo "==> Step 5: Setting up systemd services..."
CURRENT_USER="$(whoami)"

# 1. API
sudo tee /etc/systemd/system/web-observer-api.service > /dev/null << EOF
[Unit]
Description=Web Observer FastAPI API
After=network.target

[Service]
User=$CURRENT_USER
WorkingDirectory=$BACKEND_DIR
ExecStart=$BACKEND_DIR/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8002
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 2. Scheduler
sudo tee /etc/systemd/system/web-observer-scheduler.service > /dev/null << EOF
[Unit]
Description=Web Observer Postgres Scheduler
After=network.target web-observer-api.service

[Service]
User=$CURRENT_USER
WorkingDirectory=$BACKEND_DIR
ExecStart=$BACKEND_DIR/.venv/bin/python -m app.scheduler
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 3. HTTP Worker
sudo tee /etc/systemd/system/web-observer-worker-http.service > /dev/null << EOF
[Unit]
Description=Web Observer Dramatiq HTTP & Notifications Worker
After=network.target

[Service]
User=$CURRENT_USER
WorkingDirectory=$BACKEND_DIR
ExecStart=$BACKEND_DIR/.venv/bin/dramatiq app.workers --queues http_checks notifications --processes 1 --threads 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 4. Browser Worker
sudo tee /etc/systemd/system/web-observer-worker-browser.service > /dev/null << EOF
[Unit]
Description=Web Observer Dramatiq Browser Worker
After=network.target

[Service]
User=$CURRENT_USER
WorkingDirectory=$BACKEND_DIR
ExecStart=$BACKEND_DIR/.venv/bin/dramatiq app.workers --queues browser_checks --processes 1 --threads 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now web-observer-api web-observer-scheduler web-observer-worker-http web-observer-worker-browser

echo "==> All services created and started!"
echo "Check status using:"
echo "  sudo systemctl status web-observer-api"
echo "  sudo systemctl status web-observer-scheduler"
echo "  sudo systemctl status web-observer-worker-http"
echo "  sudo systemctl status web-observer-worker-browser"
