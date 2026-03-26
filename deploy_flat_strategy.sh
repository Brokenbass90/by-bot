#!/bin/bash
# ============================================================
# Deploy: ARF1 flat resistance fade + ASC1 5m confirmation
# Run this on your LOCAL machine (not the VM) then SSH to server
# ============================================================

set -e

BRANCH="codex/dynamic-symbol-filters"
SERVER="root@64.226.73.119"
BOT_DIR="/root/bybit-bot-clean-v28"
ENV_FILE="$BOT_DIR/.env"

echo "=== Step 1: Push branch from local machine ==="
echo "Run this on your local machine:"
echo "  git push origin $BRANCH"
echo ""

echo "=== Step 2: SSH to server and deploy ==="
echo "  ssh $SERVER"
echo ""
echo "Then on the server:"
cat <<'SSHSCRIPT'
cd /root/bybit-bot-clean-v28

# Pull latest code
git fetch origin
git checkout codex/dynamic-symbol-filters
git pull origin codex/dynamic-symbol-filters

echo "=== Step 3: Update .env ==="
# Add/update these lines in .env

# --- ASC1: add LINK to allowlist ---
# Change:  ASC1_SYMBOL_ALLOWLIST=ATOMUSDT
# To:      ASC1_SYMBOL_ALLOWLIST=ATOMUSDT,LINKUSDT

# --- ASC1: enable 5m confirmation ---
# Add:     ASC1_CONFIRM_5M_BARS=6

# --- ARF1 (new flat resistance fade) ---
# Add:     ENABLE_FLAT_TRADING=1
# Add:     ARF1_SYMBOL_ALLOWLIST=LINKUSDT,LTCUSDT,SUIUSDT,DOTUSDT
# Add:     FLAT_RISK_MULT=0.10
# Add:     FLAT_MAX_OPEN_TRADES=1

# Use sed to update ASC1_SYMBOL_ALLOWLIST
sed -i 's/^ASC1_SYMBOL_ALLOWLIST=.*/ASC1_SYMBOL_ALLOWLIST=ATOMUSDT,LINKUSDT/' .env

# Add new lines (only if not already present)
grep -q '^ASC1_CONFIRM_5M_BARS=' .env || echo 'ASC1_CONFIRM_5M_BARS=6' >> .env
grep -q '^ENABLE_FLAT_TRADING=' .env || echo 'ENABLE_FLAT_TRADING=1' >> .env
grep -q '^ARF1_SYMBOL_ALLOWLIST=' .env || echo 'ARF1_SYMBOL_ALLOWLIST=LINKUSDT,LTCUSDT,SUIUSDT,DOTUSDT' >> .env
grep -q '^FLAT_RISK_MULT=' .env || echo 'FLAT_RISK_MULT=0.10' >> .env
grep -q '^FLAT_MAX_OPEN_TRADES=' .env || echo 'FLAT_MAX_OPEN_TRADES=1' >> .env

echo "=== .env changes applied ==="
grep -E 'ASC1_SYMBOL_ALLOWLIST|ASC1_CONFIRM_5M_BARS|ENABLE_FLAT|ARF1_SYMBOL|FLAT_RISK|FLAT_MAX' .env

echo "=== Step 4: Restart bot ==="
# Find the running bot process
BOT_PID=$(pgrep -f smart_pump_reversal_bot.py || echo "")
if [ -n "$BOT_PID" ]; then
    echo "Stopping bot PID $BOT_PID..."
    kill $BOT_PID
    sleep 3
fi

# Start bot (adjust this to match how you normally start it)
nohup python3 smart_pump_reversal_bot.py > logs/bot_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo "Bot started PID $!"
SSHSCRIPT
