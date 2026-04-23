#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_IP="${SERVER_IP:-64.226.73.119}"
SERVER_USER="${SERVER_USER:-root}"
SERVER_BOT_DIR="${SERVER_BOT_DIR:-/root/by-bot}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/by-bot}"
SERVICE_NAME="${SERVICE_NAME:-trading-journal-web}"

SSH_OPTS=(-o StrictHostKeyChecking=no)
if [[ -n "${SSH_KEY:-}" && -f "${SSH_KEY}" ]]; then
  SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=no)
fi

cd "$ROOT"

required_local=(
  "web/main.py"
  "web/auth.py"
  "web/deps.py"
  "web/routes/data_routes.py"
  "web/routes/ai_routes.py"
  "web/routes/auth_routes.py"
  "web/routes/admin_routes.py"
  "web/static/index.html"
  "scripts/run_web.sh"
  "configs/web_config.json"
)

for rel in "${required_local[@]}"; do
  if [[ ! -f "$rel" ]]; then
    echo "[deploy-web] missing local file: $rel" >&2
    exit 1
  fi
done

echo "[deploy-web] uploading web files to $SERVER_USER@$SERVER_IP:$SERVER_BOT_DIR"
ssh "${SSH_OPTS[@]}" "$SERVER_USER@$SERVER_IP" "mkdir -p '$SERVER_BOT_DIR/web/routes' '$SERVER_BOT_DIR/web/static' '$SERVER_BOT_DIR/scripts' '$SERVER_BOT_DIR/configs'"
scp "${SSH_OPTS[@]}" web/main.py "$SERVER_USER@$SERVER_IP:$SERVER_BOT_DIR/web/main.py" >/dev/null
scp "${SSH_OPTS[@]}" web/auth.py "$SERVER_USER@$SERVER_IP:$SERVER_BOT_DIR/web/auth.py" >/dev/null
scp "${SSH_OPTS[@]}" web/deps.py "$SERVER_USER@$SERVER_IP:$SERVER_BOT_DIR/web/deps.py" >/dev/null
scp "${SSH_OPTS[@]}" web/routes/data_routes.py "$SERVER_USER@$SERVER_IP:$SERVER_BOT_DIR/web/routes/data_routes.py" >/dev/null
scp "${SSH_OPTS[@]}" web/routes/ai_routes.py "$SERVER_USER@$SERVER_IP:$SERVER_BOT_DIR/web/routes/ai_routes.py" >/dev/null
scp "${SSH_OPTS[@]}" web/routes/auth_routes.py "$SERVER_USER@$SERVER_IP:$SERVER_BOT_DIR/web/routes/auth_routes.py" >/dev/null
scp "${SSH_OPTS[@]}" web/routes/admin_routes.py "$SERVER_USER@$SERVER_IP:$SERVER_BOT_DIR/web/routes/admin_routes.py" >/dev/null
scp "${SSH_OPTS[@]}" web/static/index.html "$SERVER_USER@$SERVER_IP:$SERVER_BOT_DIR/web/static/index.html" >/dev/null
scp "${SSH_OPTS[@]}" scripts/run_web.sh "$SERVER_USER@$SERVER_IP:$SERVER_BOT_DIR/scripts/run_web.sh" >/dev/null
scp "${SSH_OPTS[@]}" configs/web_config.json "$SERVER_USER@$SERVER_IP:$SERVER_BOT_DIR/configs/web_config.json" >/dev/null

echo "[deploy-web] installing systemd service $SERVICE_NAME"
ssh "${SSH_OPTS[@]}" "$SERVER_USER@$SERVER_IP" "cat >/etc/systemd/system/$SERVICE_NAME.service <<'UNIT'
[Unit]
Description=Trading Journal Private Web
After=network.target

[Service]
Type=simple
WorkingDirectory=$SERVER_BOT_DIR
Environment=WEB_HOST=127.0.0.1
Environment=WEB_PORT=8765
Environment=WEB_RUNTIME_ROOT=$SERVER_BOT_DIR/runtime
Environment=WEB_COOKIE_SECURE=0
ExecStart=/bin/bash $SERVER_BOT_DIR/scripts/run_web.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now $SERVICE_NAME
sleep 2
systemctl --no-pager --full status $SERVICE_NAME | sed -n '1,30p'
curl -fsS http://127.0.0.1:8765/ping"

echo
echo "[deploy-web] done"
echo "[deploy-web] local laptop/desktop access:"
echo "  ssh -i $SSH_KEY -N -L 8765:127.0.0.1:8765 $SERVER_USER@$SERVER_IP"
echo "  then open http://127.0.0.1:8765"
