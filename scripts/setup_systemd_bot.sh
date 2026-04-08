#!/usr/bin/env bash
# setup_systemd_bot.sh
# Run this ON THE SERVER (as root) to install the bot as a systemd service.
# After this: bot starts on boot, auto-restarts on crash, logs go to journald.
#
# Usage:
#   bash scripts/setup_systemd_bot.sh
#
# To check status:
#   systemctl status bybit-bot
#   journalctl -u bybit-bot -f
#
# To restart manually:
#   systemctl restart bybit-bot
set -euo pipefail

BOT_DIR="${BOT_DIR:-/root/by-bot}"
BOT_USER="${BOT_USER:-root}"
VENV_PYTHON="$BOT_DIR/.venv/bin/python3"
SERVICE_FILE="/etc/systemd/system/bybit-bot.service"

echo "══════════════════════════════════════════"
echo "  Installing bybit-bot systemd service"
echo "  bot_dir=$BOT_DIR"
echo "══════════════════════════════════════════"

# Validate bot directory
if [[ ! -f "$BOT_DIR/smart_pump_reversal_bot.py" ]]; then
  echo "ERROR: smart_pump_reversal_bot.py not found in $BOT_DIR"
  exit 1
fi

if [[ ! -f "$VENV_PYTHON" ]]; then
  echo "ERROR: venv python not found at $VENV_PYTHON"
  echo "  Run: cd $BOT_DIR && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

# Write service file
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Bybit Trading Bot (smart_pump_reversal_bot)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=600
StartLimitBurst=5

[Service]
Type=simple
User=$BOT_USER
WorkingDirectory=$BOT_DIR
ExecStart=$VENV_PYTHON -u smart_pump_reversal_bot.py
Restart=on-failure
RestartSec=10
# Exponential backoff: wait longer after repeated crashes
RestartSteps=5
RestartMaxDelaySec=120

# Log settings
StandardOutput=append:$BOT_DIR/runtime/live.out
StandardError=append:$BOT_DIR/runtime/live.out

# Environment
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$BOT_DIR/.env

# Resource limits — prevent runaway memory usage
MemoryMax=2G
OOMScoreAdjust=500

# Graceful shutdown: give bot 30s to close positions cleanly
TimeoutStopSec=30
KillMode=mixed
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Service file written to $SERVICE_FILE"

# Reload systemd and enable
systemctl daemon-reload
systemctl enable bybit-bot
echo "✅ Service enabled (will start on boot)"

# Check if already running via screen and offer migration
if screen -list 2>/dev/null | grep -q "\.bot"; then
  echo ""
  echo "⚠️  Found existing screen session. Migrating..."
  screen -S bot -X quit 2>/dev/null || true
  sleep 2
  echo "   Screen session stopped."
fi

# Start the service
systemctl start bybit-bot
sleep 5

# Verify
if systemctl is-active --quiet bybit-bot; then
  echo "✅ bybit-bot is running via systemd"
  systemctl status bybit-bot --no-pager -l | head -20
else
  echo "❌ bybit-bot failed to start — check: journalctl -u bybit-bot -n 50"
  exit 1
fi

echo ""
echo "Done. Useful commands:"
echo "  systemctl status bybit-bot       — status"
echo "  systemctl restart bybit-bot      — restart"
echo "  systemctl stop bybit-bot         — stop"
echo "  journalctl -u bybit-bot -f       — follow logs"
echo "  journalctl -u bybit-bot -n 100   — last 100 lines"
