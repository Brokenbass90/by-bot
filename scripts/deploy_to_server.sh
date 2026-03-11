#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# deploy_to_server.sh
# Run this on your LOCAL machine (not the server) to:
#  1. Push latest commits to GitHub
#  2. SSH into the DigitalOcean server
#  3. Pull latest code
#  4. Restart the bot
#
# Prerequisites:
#   - git credentials configured on local machine
#   - SSH access to server (key or password)
#   - SERVER_IP env var set (or edit DEFAULT_IP below)
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

BRANCH="${GIT_BRANCH:-codex/dynamic-symbol-filters}"
SERVER_IP="${SERVER_IP:-64.226.73.119}"
SERVER_USER="${SERVER_USER:-root}"
BOT_DIR="${BOT_DIR:-/root/bybit-bot-clean-v28}"    # adjust if needed
BOT_SCREEN="${BOT_SCREEN:-bot}"                     # screen/tmux session name

echo "══════════════════════════════════════════"
echo "  BOT DEPLOY — $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "  branch=$BRANCH  server=$SERVER_IP"
echo "══════════════════════════════════════════"

# ── 1. Push to GitHub ────────────────────────────────────────────
echo ""
echo "→ [1/3] Pushing to GitHub..."
git push origin "$BRANCH"
echo "   ✅ pushed"

# ── 2+3. SSH to server: pull + restart ───────────────────────────
echo ""
echo "→ [2/3] Connecting to server $SERVER_USER@$SERVER_IP..."
ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" bash <<ENDSSH
set -e
cd "$BOT_DIR"
echo "  → git pull"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull origin "$BRANCH"
echo "  ✅ code updated"

# Copy new config files if they don't exist on server
[ -f configs/news_filter/events.csv ] || mkdir -p runtime/news_filter
[ -f runtime/news_filter/events.csv ] || cp configs/alpaca_paper_local.env.example configs/alpaca_paper_local.env 2>/dev/null || true

echo "  → restarting bot..."
# Try screen first, fall back to systemctl
if screen -list | grep -q "$BOT_SCREEN"; then
    screen -S "$BOT_SCREEN" -X quit || true
    sleep 2
fi
if command -v systemctl &>/dev/null && systemctl is-active --quiet bot 2>/dev/null; then
    systemctl restart bot
    echo "  ✅ bot restarted via systemctl"
elif [ -f scripts/start_bot.sh ]; then
    screen -dmS "$BOT_SCREEN" bash scripts/start_bot.sh
    echo "  ✅ bot restarted in screen session: $BOT_SCREEN"
else
    echo "  ⚠️  No start script found — restart bot manually"
fi

echo "  → post-deploy checks:"
echo "  git log --oneline -3:"
git log --oneline -3
ENDSSH

echo ""
echo "══════════════════════════════════════════"
echo "  DEPLOY COMPLETE"
echo "══════════════════════════════════════════"
