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
SERVICE_NAME="${SERVICE_NAME:-bybot}"
SSH_KEY="${SSH_KEY:-}"
LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_KEY="$HOME/.ssh/by-bot"

if [[ -z "$SSH_KEY" && -f "$DEFAULT_KEY" ]]; then
  SSH_KEY="$DEFAULT_KEY"
fi

if [[ -n "$SSH_KEY" ]]; then
  SSH_CMD="ssh -i $SSH_KEY -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP"
  SCP_CMD="scp -i $SSH_KEY -o StrictHostKeyChecking=no"
else
  SSH_CMD="ssh -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP"
  SCP_CMD="scp -o StrictHostKeyChecking=no"
fi

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
  "bot/allowlist_watcher.py"
  "bot/chart_geometry.py"
  "bot/diagnostics.py"
  "bot/deepseek_overlay.py"
  "bot/deepseek_autoresearch_agent.py"
  "bot/geometry_cache.py"
  "bot/operator_snapshot.py"
  "bot/router_geometry.py"
  "bot/strategy_health_timeline.py"
  "strategies/elder_triple_screen_v2.py"
  "strategies/impulse_volume_breakout_v1.py"
  "scripts/setup_systemd_bot.sh"
  "scripts/bot_health_watchdog.sh"
  "scripts/setup_watchdog_cron.sh"
  "scripts/check_control_plane_health.sh"
  "scripts/apply_live_control_plane_env_patch.py"
  "scripts/control_plane_watchdog.py"
  "scripts/build_regime_state.py"
  "scripts/build_symbol_router.py"
  "scripts/dynamic_allowlist.py"
  "scripts/build_portfolio_allocator.py"
  "scripts/build_geometry_state.py"
  "scripts/build_operator_snapshot.py"
  "scripts/build_router_symbol_memory.py"
  "scripts/auto_apply_research_winner.py"
  "scripts/equities_alpaca_paper_bridge.py"
  "scripts/refresh_router_backtest_gate.py"
  "scripts/run_nightly_research_queue.py"
  "scripts/router_quality_audit.py"
  "scripts/build_strategy_health_timeline.py"
  "scripts/evaluate_crypto_promotion.py"
  "scripts/setup_server_crons.sh"
  "scripts/deploy_foundation.sh"
  "configs/crypto_promotion_policy.json"
  "configs/portfolio_allocator_policy.json"
  "configs/research_nightly_queue.json"
  "configs/strategy_profile_registry.json"
  "configs/autoresearch/bear_chop_plus_range_probe_v1.json"
  "configs/autoresearch/range_scalp_v1_annual_focus_v2.json"
  "configs/autoresearch/ivb1_live_canary_annual_focus_v1.json"
  "configs/autoresearch/flat_live_universe_repair_v1.json"
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
echo "→ [2/5] Installing/updating systemd service..."
SYSTEMD_INSTALL_OK=1
if ! $SSH_CMD "BOT_DIR=$BOT_DIR SERVICE_NAME=$SERVICE_NAME bash $BOT_DIR/scripts/setup_systemd_bot.sh"; then
  SYSTEMD_INSTALL_OK=0
  echo "   ⚠️ systemd service install/start reported failure; continuing with env+cron repair"
else
  echo "   ✅ systemd service installed"
fi

# ── 3. Install/update control-plane and watchdog crons ────────────
echo ""
echo "→ [3/5] Installing control-plane crons + watchdog cron..."
$SSH_CMD "cd $BOT_DIR && .venv/bin/python scripts/apply_live_control_plane_env_patch.py && bash scripts/setup_server_crons.sh >/tmp/foundation_crons.log 2>&1 && tail -n 20 /tmp/foundation_crons.log"
$SSH_CMD "BOT_DIR=$BOT_DIR bash $BOT_DIR/scripts/setup_watchdog_cron.sh"
echo "   ✅ control-plane + watchdog crons installed"

# ── 4. Install control-plane health check cron ───────────────────
echo ""
echo "→ [4/5] Installing control-plane health check cron (every 30 min)..."
$SSH_CMD bash <<ENDSSH
BOT_DIR=$BOT_DIR
LOG_DIR=\$BOT_DIR/runtime
SERVICE_NAME=$SERVICE_NAME
CRON_COMMENT="\${SERVICE_NAME}_cp_health"
LEGACY_CRON_COMMENT="bybit_cp_health"
SCRIPT="\$BOT_DIR/scripts/check_control_plane_health.sh"
mkdir -p "\$LOG_DIR"
chmod +x "\$SCRIPT"
CRON_LINE="*/30 * * * * /bin/bash -lc 'BOT_DIR=\$BOT_DIR \$SCRIPT >> \$LOG_DIR/cp_health.log 2>&1' # \$CRON_COMMENT"
(crontab -l 2>/dev/null | grep -v "\$CRON_COMMENT" | grep -v "\$LEGACY_CRON_COMMENT" || true; echo "\$CRON_LINE") | crontab -
echo "Installed:"
crontab -l | grep "\$CRON_COMMENT"
ENDSSH
echo "   ✅ control-plane health cron installed"

# ── 5. Verify bot is running ──────────────────────────────────────
echo ""
echo "→ [5/5] Verifying bot status..."
sleep 3
$SSH_CMD "systemctl reset-failed $SERVICE_NAME >/dev/null 2>&1 || true; systemctl restart $SERVICE_NAME >/dev/null 2>&1 || systemctl start $SERVICE_NAME >/dev/null 2>&1 || true; sleep 5; systemctl status $SERVICE_NAME --no-pager -l | head -15"

echo ""
echo "══════════════════════════════════════════"
echo "  FOUNDATION DEPLOY COMPLETE"
echo ""
echo "  Bot is now managed by systemd:"
echo "    systemctl status $SERVICE_NAME"
echo "    systemctl restart $SERVICE_NAME"
echo "    journalctl -u $SERVICE_NAME -f"
echo ""
echo "  Watchdog runs every 2 minutes:"
echo "    tail -f $BOT_DIR/runtime/watchdog.log"
echo ""
echo "  Control-plane check runs every 30 minutes:"
echo "    tail -f $BOT_DIR/runtime/cp_health.log"
if [[ "$SYSTEMD_INSTALL_OK" -ne 1 ]]; then
  echo ""
  echo "  NOTE:"
  echo "    systemd failed on the first install/start attempt,"
  echo "    but env patch + cron repair still completed and final restart was attempted."
fi
echo "══════════════════════════════════════════"
