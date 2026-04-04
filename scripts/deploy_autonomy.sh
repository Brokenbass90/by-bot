#!/usr/bin/env bash
# deploy_autonomy.sh
# ==================
# Deploys all AI autonomy files to the production server.
# Adds required crons (equity_curve_autopilot + deepseek_weekly_cron).
# Restarts the bot service.
#
# Usage (from project root on local machine):
#   bash scripts/deploy_autonomy.sh
#   bash scripts/deploy_autonomy.sh --dry-run   # show what would be copied, no action
#
# Prerequisites:
#   SSH key at ~/.ssh/by-bot (or set SSH_KEY env var)
#   Server: 64.226.73.119, user root, bot dir /root/by-bot
#
# What this deploys:
#   bot/health_gate.py              — live entry gating by equity curve
#   bot/allowlist_watcher.py        — hot-reload of symbol allowlists
#   bot/deepseek_research_gate.py   — safety tier for DeepSeek autonomy
#   bot/deepseek_overlay.py         — DeepSeek API client + prompting
#   bot/deepseek_autoresearch_agent.py — AI param tuning agent
#   bot/deepseek_action_executor.py — /ai_deploy executor
#   bot/trade_learning_loop.py      — per-trade pattern learning
#   bot/family_profiles.py          — per-symbol-family param multipliers
#   configs/family_profiles.json    — multiplier values (hot-reloadable)
#   configs/approved_specs.txt      — TIER1 AUTO specs for research gate
#   scripts/deepseek_weekly_cron.py — weekly audit + AI trigger cron
#   scripts/equity_curve_autopilot.py — generates strategy_health.json weekly
#   scripts/equities_alpaca_paper_bridge.py — Alpaca monthly paper bridge
#   scripts/build_equities_intraday_watchlist.py — dynamic equities watchlist builder
#   scripts/equities_monthly_research_sim.py — monthly equities research engine
#   scripts/run_equities_alpaca_monthly_autopilot.sh — monthly autopilot wrapper
#   scripts/run_equities_alpaca_v36_candidate.sh — pinned v36 paper candidate
#   scripts/run_equities_monthly_v36_refresh.sh — v36 refresh pipeline
#   configs/alpaca_paper_v36_candidate.env — v36 paper candidate env

set -euo pipefail

SERVER_IP="64.226.73.119"
SERVER_USER="root"
BOT_DIR="/root/by-bot"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/by-bot}"
DRY_RUN=0

for arg in "$@"; do
  if [[ "$arg" == "--dry-run" ]]; then
    DRY_RUN=1
  fi
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

SSH_OPTS="-i $SSH_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10"
SSH_CMD="ssh $SSH_OPTS"
RSYNC_CMD="rsync -avz --checksum -e \"ssh $SSH_OPTS\""

echo "=========================================="
echo "  deploy_autonomy.sh"
echo "  Server : $SERVER_USER@$SERVER_IP:$BOT_DIR"
echo "  DRY_RUN: $DRY_RUN"
echo "=========================================="

# ── Files to deploy ────────────────────────────────────────────────────────────
BOT_FILES=(
    "bot/health_gate.py"
    "bot/allowlist_watcher.py"
    "bot/deepseek_research_gate.py"
    "bot/deepseek_overlay.py"
    "bot/deepseek_autoresearch_agent.py"
    "bot/deepseek_action_executor.py"
    "bot/trade_learning_loop.py"
    "bot/family_profiles.py"
)

CONFIG_FILES=(
    "configs/family_profiles.json"
    "configs/approved_specs.txt"
    "configs/alpaca_paper_v36_candidate.env"
)

SCRIPT_FILES=(
    "scripts/deepseek_weekly_cron.py"
    "scripts/equity_curve_autopilot.py"
    "scripts/build_equities_intraday_watchlist.py"
    "scripts/equities_midmonth_monitor.py"
    "scripts/equities_alpaca_paper_bridge.py"
    "scripts/equities_alpaca_intraday_bridge.py"
    "scripts/equities_monthly_research_sim.py"
    "scripts/run_equities_alpaca_monthly_autopilot.sh"
    "scripts/run_equities_alpaca_v36_candidate.sh"
    "scripts/run_equities_monthly_v36_refresh.sh"
    "configs/intraday_config.json"
)

# ── Syntax check before deploying ─────────────────────────────────────────────
echo ""
echo "── Syntax checks ──"
ALL_OK=1
for f in "${BOT_FILES[@]}" "${SCRIPT_FILES[@]}"; do
    if [[ "$f" == *.py ]]; then
        if python3 -m py_compile "$PROJECT_ROOT/$f" 2>/dev/null; then
            echo "  ✅ $f"
        else
            echo "  ❌ SYNTAX ERROR: $f"
            ALL_OK=0
        fi
    fi
done

if [[ $ALL_OK -eq 0 ]]; then
    echo "ABORT: syntax errors found. Fix before deploying."
    exit 1
fi

if [[ $DRY_RUN -eq 1 ]]; then
    echo ""
    echo "── DRY RUN — files that would be copied ──"
    for f in "${BOT_FILES[@]}" "${CONFIG_FILES[@]}" "${SCRIPT_FILES[@]}"; do
        echo "  $PROJECT_ROOT/$f  →  $SERVER_USER@$SERVER_IP:$BOT_DIR/$f"
    done
    echo ""
    echo "DRY RUN complete. Use without --dry-run to deploy."
    exit 0
fi

# ── Copy files ─────────────────────────────────────────────────────────────────
echo ""
echo "── Copying bot/ files ──"
for f in "${BOT_FILES[@]}"; do
    rsync -avz --checksum -e "ssh $SSH_OPTS" \
        "$PROJECT_ROOT/$f" \
        "$SERVER_USER@$SERVER_IP:$BOT_DIR/$f"
done

echo ""
echo "── Copying configs/ files ──"
for f in "${CONFIG_FILES[@]}"; do
    rsync -avz --checksum -e "ssh $SSH_OPTS" \
        "$PROJECT_ROOT/$f" \
        "$SERVER_USER@$SERVER_IP:$BOT_DIR/$f"
done

echo ""
echo "── Copying scripts/ files ──"
for f in "${SCRIPT_FILES[@]}"; do
    rsync -avz --checksum -e "ssh $SSH_OPTS" \
        "$PROJECT_ROOT/$f" \
        "$SERVER_USER@$SERVER_IP:$BOT_DIR/$f"
done

# ── Verify imports on server ───────────────────────────────────────────────────
echo ""
echo "── Verifying imports on server ──"
$SSH_CMD "$SERVER_USER@$SERVER_IP" bash <<ENDSSH
cd $BOT_DIR
echo -n "  health_gate: "
python3 -c "from bot.health_gate import gate; print('OK —', gate.status_summary())" 2>&1 || echo "FAIL"

echo -n "  family_profiles: "
python3 -c "from bot.family_profiles import profiles; v=profiles.scale('BTCUSDT','sl',1.0); print(f'OK — BTC sl mult={v}')" 2>&1 || echo "FAIL"

echo -n "  research_gate: "
python3 -c "from bot.deepseek_research_gate import gate; print('OK —', gate.status_report()[:60])" 2>&1 || echo "FAIL"

echo -n "  trade_learning_loop: "
python3 -c "from bot.trade_learning_loop import trade_learning; print('OK')" 2>&1 || echo "FAIL"

echo -n "  deepseek_overlay: "
python3 -c "from bot.deepseek_overlay import DeepSeekOverlay; print('OK')" 2>&1 || echo "FAIL"
ENDSSH

# ── Restart bot service ────────────────────────────────────────────────────────
echo ""
echo "── Restarting bot service ──"
$SSH_CMD "$SERVER_USER@$SERVER_IP" bash <<'ENDSSH'
# Try common service names
for SVC in bybot bot bybit-bot; do
    if systemctl is-active --quiet "$SVC" 2>/dev/null || systemctl status "$SVC" &>/dev/null; then
        echo "  Restarting service: $SVC"
        systemctl restart "$SVC"
        sleep 3
        systemctl status "$SVC" --no-pager | head -6
        break
    fi
done
ENDSSH

# ── Set up crons ───────────────────────────────────────────────────────────────
echo ""
echo "── Setting up crons ──"
$SSH_CMD "$SERVER_USER@$SERVER_IP" bash <<ENDSSH
cd $BOT_DIR

# Add crons if not already present
CRON_WEEKLY_AUDIT="0 8 * * 1 cd $BOT_DIR && source configs/local.env 2>/dev/null; python3 scripts/deepseek_weekly_cron.py >> logs/deepseek_weekly.log 2>&1"
CRON_EQUITY_CURVE="0 9 * * 1 cd $BOT_DIR && python3 scripts/equity_curve_autopilot.py >> logs/equity_curve.log 2>&1"
CRON_MIDMONTH="0 15 * * 3 cd $BOT_DIR && source configs/alpaca_paper_local.env 2>/dev/null; python3 scripts/equities_midmonth_monitor.py >> logs/alpaca_midmonth.log 2>&1"

mkdir -p logs

(crontab -l 2>/dev/null; echo "") | grep -v "deepseek_weekly_cron\|equity_curve_autopilot\|equities_midmonth_monitor" > /tmp/crontab_new.txt
echo "\$CRON_WEEKLY_AUDIT" >> /tmp/crontab_new.txt
echo "\$CRON_EQUITY_CURVE" >> /tmp/crontab_new.txt
echo "\$CRON_MIDMONTH" >> /tmp/crontab_new.txt
crontab /tmp/crontab_new.txt
echo "  Crons updated:"
crontab -l | grep -E "deepseek|equity_curve|midmonth"
ENDSSH

echo ""
echo "=========================================="
echo "  ✅ deploy_autonomy.sh COMPLETE"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Check Telegram — bot should announce restart"
echo "  2. Watch logs: ssh root@$SERVER_IP 'tail -f /root/by-bot/logs/bot.log'"
echo "  3. Test health_gate: send /ai_results in Telegram"
echo "  4. Wait until Mon 08:00 UTC for first deepseek_weekly_cron run"
echo "     OR run manually: ssh root@$SERVER_IP 'cd /root/by-bot && python3 scripts/deepseek_weekly_cron.py'"
