#!/usr/bin/env bash
set -euo pipefail

# ============================================
# AIMAS Recommendation Service - systemd deploy
# ============================================
# What this does:
# 1) Creates systemd units:
#       - aimas-app.service        (Uvicorn FastAPI health)
#       - aimas-consumer.service   (Hybrid consumer: LLM if key present, else rules)
# 2) (Optional) Creates Nginx site to proxy :80 -> :8080
#
# Requirements:
# - Ubuntu 22.04+ (root or sudo)
# - Repo cloned on the host
# - Python venv and requirements already installed
# - .env present in repo root
#
# Usage:
#   chmod +x deploy_systemd.sh
#   sudo ./deploy_systemd.sh [--with-nginx] [--user aimas] [--repo /home/aimas/aima-recommendation-service] [--port 8080]
#
# Notes:
# - Defaults assume you created user 'aimas' and cloned repo in /home/aimas/aima-recommendation-service
# - If your paths differ, pass --repo and --user accordingly

WITH_NGINX=false
APP_PORT=8080
DEPLOY_USER="aimas"
REPO_DIR="/home/${DEPLOY_USER}/df-2.0-aima-recommendation-service"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-nginx) WITH_NGINX=true; shift ;;
    --user)       DEPLOY_USER="$2"; REPO_DIR="/home/${DEPLOY_USER}/df-2.0-aima-recommendation-service"; shift 2 ;;
    --repo)       REPO_DIR="$2"; shift 2 ;;
    --port)       APP_PORT="$2"; shift 2 ;;
    *)            echo "Unknown arg: $1"; exit 1 ;;
  esac
done

echo "=== Deploying AIMAS services ==="
echo "User:        ${DEPLOY_USER}"
echo "Repo:        ${REPO_DIR}"
echo "App port:    ${APP_PORT}"
echo "With Nginx:  ${WITH_NGINX}"
echo "================================"

# Sanity checks
if [[ ! -d "${REPO_DIR}" ]]; then
  echo "Oops! Repo directory not found: ${REPO_DIR}"
  echo "   Clone first: git clone <repo> ${REPO_DIR}"
  exit 1
fi

if [[ ! -f "${REPO_DIR}/.env" ]]; then
  echo "Oops! Missing .env at ${REPO_DIR}/.env"
  echo "   Create it before deploying."
  exit 1
fi

if [[ ! -x "${REPO_DIR}/.venv/bin/python" ]]; then
  echo "❌ Python venv not found at ${REPO_DIR}/.venv"
  echo "   Create it and install deps:"
  echo "     cd ${REPO_DIR}"
  echo "     python3 -m venv .venv && source .venv/bin/activate"
  echo "     pip install -r requirements.txt"
  exit 1
fi

# Paths
PY_BIN="${REPO_DIR}/.venv/bin/python"
UVICORN_BIN="${REPO_DIR}/.venv/bin/uvicorn"
ENV_FILE="${REPO_DIR}/.env"

# Create systemd service: Health API
cat <<EOF | sudo tee /etc/systemd/system/aimas-app.service >/dev/null
[Unit]
Description=AIMAS Health API
After=network.target

[Service]
User=${DEPLOY_USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${UVICORN_BIN} app:app --host 0.0.0.0 --port ${APP_PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create systemd service: Consumer (hybrid)
cat <<EOF | sudo tee /etc/systemd/system/aimas-consumer.service >/dev/null
[Unit]
Description=AIMAS Recommendation Consumer (LLM if key, else rules)
After=network.target

[Service]
User=${DEPLOY_USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${PY_BIN} consumer.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# systemd reload + enable + start
sudo systemctl daemon-reload
sudo systemctl enable aimas-app.service aimas-consumer.service
sudo systemctl restart aimas-app.service aimas-consumer.service

echo " systemd services started."
echo "   - journalctl -u aimas-app -f"
echo "   - journalctl -u aimas-consumer -f"

# Optional Nginx reverse proxy
if [[ "${WITH_NGINX}" == "true" ]]; then
  if ! command -v nginx >/dev/null 2>&1; then
    echo " Installing nginx..."
    sudo apt update && sudo apt install -y nginx
  fi

  # Create site config
  sudo tee /etc/nginx/sites-available/aimas >/dev/null <<NGX
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
NGX

  # Enable site
  if [[ ! -e /etc/nginx/sites-enabled/aimas ]]; then
    sudo ln -s /etc/nginx/sites-available/aimas /etc/nginx/sites-enabled/aimas
  fi

  # Disable default if present (optional)
  if [[ -e /etc/nginx/sites-enabled/default ]]; then
    sudo rm -f /etc/nginx/sites-enabled/default
  fi

  sudo nginx -t
  sudo systemctl reload nginx
  echo "Yes!!!... Nginx proxy active: http://13.53.197.97/health/live"
fi

echo "Done!. Services should be up."
