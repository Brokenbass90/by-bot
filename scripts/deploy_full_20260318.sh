#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# FULL DEPLOY — 2026-03-18
# Run this on your Mac from the project root:
#   cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
#   bash scripts/deploy_full_20260318.sh
#
# What it does:
#   1. Pushes latest commits to GitHub
#   2. SSHs into the server
#   3. Pulls latest code
#   4. Updates .env (BREAKOUT_QUALITY_MIN_SCORE=0.0)
#   5. Restarts the bot
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

BRANCH="codex/dynamic-symbol-filters"
SERVER_IP="64.226.73.119"
SERVER_USER="root"
BOT_DIR="/root/by-bot"
SSH_KEY="$HOME/.ssh/by-bot"

# Check if SSH key exists in default location, try project .ssh too
if [ ! -f "$SSH_KEY" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
    # Try common locations
    for K in "$PROJECT_ROOT/.ssh/by-bot" "$HOME/.ssh/id_ed25519" "$HOME/.ssh/id_rsa"; do
        if [ -f "$K" ]; then
            SSH_KEY="$K"
            break
        fi
    done
fi

SSH_CMD="ssh -i $SSH_KEY -o StrictHostKeyChecking=no"

echo "══════════════════════════════════════════════"
echo "  FULL DEPLOY — $(date '+%Y-%m-%d %H:%M:%S')"
echo "  branch=$BRANCH  server=$SERVER_IP"
echo "  ssh_key=$SSH_KEY"
echo "══════════════════════════════════════════════"

# ── 1. Push to GitHub ──────────────────────────────────────
echo ""
echo "→ [1/4] Pushing to GitHub..."
GIT_SSH_COMMAND="$SSH_CMD" git push origin "$BRANCH" 2>&1 || {
    echo "  ⚠️  Push failed. Trying with default SSH..."
    git push origin "$BRANCH" 2>&1
}
echo "  ✅ Pushed to GitHub"

# ── 2. SSH: Pull code ─────────────────────────────────────
echo ""
echo "→ [2/4] Pulling code on server..."
$SSH_CMD "$SERVER_USER@$SERVER_IP" bash <<ENDSSH
set -e
cd $BOT_DIR
echo "  Current branch: \$(git branch --show-current)"
git fetch origin $BRANCH
git checkout $BRANCH 2>/dev/null || true
git pull origin $BRANCH
echo "  ✅ Code updated"
echo "  Latest commits:"
git log --oneline -3
ENDSSH

# ── 3. Update .env on server ──────────────────────────────
echo ""
echo "→ [3/4] Updating .env on server..."
$SSH_CMD "$SERVER_USER@$SERVER_IP" bash <<'ENDSSH'
set -e
cd /root/by-bot

# Fix quality gate
if grep -q "BREAKOUT_QUALITY_MIN_SCORE" .env 2>/dev/null; then
    sed -i 's/BREAKOUT_QUALITY_MIN_SCORE=.*/BREAKOUT_QUALITY_MIN_SCORE=0.0/' .env
    echo "  ✅ Updated BREAKOUT_QUALITY_MIN_SCORE=0.0"
else
    echo "BREAKOUT_QUALITY_MIN_SCORE=0.0" >> .env
    echo "  ✅ Added BREAKOUT_QUALITY_MIN_SCORE=0.0"
fi

# Verify
echo "  Current value:"
grep "BREAKOUT_QUALITY_MIN_SCORE" .env || echo "  (not found)"

# Show key strategy flags
echo ""
echo "  Strategy flags:"
grep -E "^ENABLE_" .env 2>/dev/null || echo "  (none found)"
ENDSSH

# ── 4. Restart bot ─────────────────────────────────────────
echo ""
echo "→ [4/4] Restarting bot..."
$SSH_CMD "$SERVER_USER@$SERVER_IP" bash <<'ENDSSH'
set -e
cd /root/by-bot

# Try different restart methods
if command -v systemctl &>/dev/null && systemctl is-active --quiet bot 2>/dev/null; then
    systemctl restart bot
    echo "  ✅ Bot restarted via systemctl"
elif screen -list 2>/dev/null | grep -q "bot"; then
    screen -S bot -X quit 2>/dev/null || true
    sleep 2
    if [ -f scripts/start_bot.sh ]; then
        screen -dmS bot bash scripts/start_bot.sh
        echo "  ✅ Bot restarted in screen session"
    else
        screen -dmS bot python3 smart_pump_reversal_bot.py
        echo "  ✅ Bot restarted in screen (direct)"
    fi
elif [ -f scripts/start_bot.sh ]; then
    screen -dmS bot bash scripts/start_bot.sh
    echo "  ✅ Bot started in new screen session"
else
    echo "  ⚠️  Could not auto-restart. Please restart manually."
fi

# Verify running
sleep 3
if screen -list 2>/dev/null | grep -q "bot"; then
    echo "  Bot screen session is running"
elif systemctl is-active --quiet bot 2>/dev/null; then
    echo "  Bot systemd service is running"
else
    echo "  ⚠️  Bot may not be running — check manually"
fi
ENDSSH

echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ DEPLOY COMPLETE"
echo "  Bot should be trading with quality gate OFF"
echo "══════════════════════════════════════════════"
