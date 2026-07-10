#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/kakaopogo}"
APP_USER="${APP_USER:-ubuntu}"
OWNER_SETUP_CODE="${OWNER_SETUP_CODE:-change-me}"
BRIDGE_KEY="${BRIDGE_KEY:-}"

if [[ ! -d "$APP_DIR" ]]; then
  echo "App directory not found: $APP_DIR"
  echo "Copy or clone the project to $APP_DIR first."
  exit 1
fi

cd "$APP_DIR"

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip curl

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

sudo install -m 0644 deploy/kakaopogo.service /etc/systemd/system/kakaopogo.service
sudo sed -i "s/^User=.*/User=${APP_USER}/" /etc/systemd/system/kakaopogo.service
sudo sed -i "s/^Group=.*/Group=${APP_USER}/" /etc/systemd/system/kakaopogo.service
sudo sed -i "s|^WorkingDirectory=.*|WorkingDirectory=${APP_DIR}|" /etc/systemd/system/kakaopogo.service
sudo sed -i "s|^Environment=OWNER_SETUP_CODE=.*|Environment=OWNER_SETUP_CODE=${OWNER_SETUP_CODE}|" /etc/systemd/system/kakaopogo.service
sudo sed -i "s|^Environment=BRIDGE_KEY=.*|Environment=BRIDGE_KEY=${BRIDGE_KEY}|" /etc/systemd/system/kakaopogo.service
sudo sed -i "s|^ExecStart=.*|ExecStart=${APP_DIR}/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000|" /etc/systemd/system/kakaopogo.service

sudo systemctl daemon-reload
sudo systemctl enable kakaopogo
sudo systemctl restart kakaopogo

echo "KakaoPoGo service status:"
sudo systemctl --no-pager --full status kakaopogo || true
echo
echo "Local health check:"
curl -fsS http://127.0.0.1:8000/health && echo
