#!/usr/bin/env bash
# deploy_foundation.sh
# Deploys the self-healing foundation to the live server:
#   1. Upload changed files
#   2. Install systemd service (replaces screen)
#   3. Install watchdog cron
#   4. Install control-plane health check cron
#   5. Verify bot is running
#
# Run from LOCAL machine:
#   SERVER_IP=64.226.73.119 bash scripts/deploy_foundation.sh
#
# Prerequisites:
#   - SSH key access to server
#   - Git repo is up to date locally
set -euo pipefail

SERVER_IP="${SERVER_IP:-64.226.73.119}"
SERVER_USER="${SERVER_USER:-root}"
BOT_DIR="${BOT_DIR:-/root/by-bot}"
LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SSH_CMD="ssh -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP"
SCP_CMD="scp -o StrictHostKeyChecking=no"

echo "══════════════════════════════════════════"
echo "  FOUNDATION DEPLOY"
echo "  server: $SERVER_USER@$SERVER_IP"
echo "  bot_dir: $BOT_DIR"
echo "  $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "══════════════════════════════════════════"

# ── 1. Upload changed files ───────────────────────────────────────
echo ""
echo "→ [1/5] Uploading files..."

FILES=(
  "smart_pump_reversal_bot.py"
  "scripts/setup_systemd_bot.sh"
  "scripts/bot_health_watchdog.sh"
  "scripts/setup_watchdog_cron.sh"
  "scripts/check_control_plane_health.sh"
  "scripts/deploy_foundation.sh"
)

for f in "${FILES[@]}"; do
  echo "   uploading $f"
  $SCP_CMD "$LOCAL_ROOT/$f" "$SERVER_USER@$SERVER_IP:$BOT_DIR/$f"
done

# Make scripts executable on server
$SSH_CMD "chmod +x $BOT_DIR/scripts/*.sh"
echo "   ✅ files uploaded"

# ── 2. Install systemd service ────────────────────────────────────
echo ""
echo "→ [2/5] Installing systemd service..."
$SSH_CMD "BOT_DIR=$BOT_DIR bash $BOT_DIR/scripts/setup_systemd_bot.sh"
echo "   ✅ systemd service installed"

# ── 3. Install watchdog cron ──────────────────────────────────────
echo ""
echo "→ [3/5] Installing watchdog cron (every 2 min)..."
$SSH_CMD "BOT_DIR=$BOT_DIR bash $BOT_DIR/scripts/setup_watchdog_cron.sh"
echo "   ✅ watchdog cron installed"

# ── 4. Install control-plane health check cron ───────────────────
echo ""
echo "→ [4/5] Installing control-plane health check cron (every 30 min)..."
$SSH_CMD bash <<ENDSSH
BOT_DIR=$BOT_DIR
LOG_DIR=\$BOT_DIR/runtime
CRON_COMMENT="bybit_cp_health"
SCRIPT="\$BOT_DIR/scripts/check_control_plane_health.sh"
mkdir -p "\$LOG_DIR"
chmod +x "\$SCRIPT"
CRON_LINE="*/30 * * * * /bin/bash -lc 'BOT_DIR=\$BOT_DIR \$SCRIPT >> \$LOG_DIR/cp_health.log 2>&1' # \$CRON_COMMENT"
(crontab -l 2>/dev/null | grep -v "\$CRON_COMMENT" || true; echo "\$CRON_LINE") | crontab -
echo "Installed:"
crontab -l | grep "\$CRON_COMMENT"
ENDSSH
echo "   ✅ control-plane health cron installed"

# ── 5. Verify bot is running ──────────────────────────────────────
echo ""
echo "→ [5/5] Verifying bot status..."
sleep 3
$SSH_CMD "systemctl status bybit-bot --no-pager -l | head -15"

echo ""
echo "══════════════════════════════════════════"
echo "  FOUNDATION DEPLOY COMPLETE"
echo ""
echo "  Bot is now managed by systemd:"
echo "    systemctl status bybit-bot"
echo "    systemctl restart bybit-bot"
echo "    journalctl -u bybit-bot -f"
echo ""
echo "  Watchdog runs every 2 minutes:"
echo "    tail -f $BOT_DIR/runtime/watchdog.log"
echo ""
echo "  Control-plane check runs every 30 minutes:"
echo "    tail -f $BOT_DIR/runtime/cp_health.log"
echo "══════════════════════════════════════════"
