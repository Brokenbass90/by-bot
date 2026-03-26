#!/bin/bash
# ================================================================
# CLEAN SERVER DEPLOY — bybit-bot-clean-v28
# Run this ON THE SERVER: ssh root@64.226.73.119
# Then:  bash /root/bybit-bot-clean-v28/scripts/clean_deploy_server.sh
# ================================================================

set -e

BOT_DIR="/root/bybit-bot-clean-v28"
BRANCH="codex/dynamic-symbol-filters"
LOG_DIR="$BOT_DIR/logs"

cd "$BOT_DIR"
mkdir -p "$LOG_DIR"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   BYBIT BOT — CLEAN DEPLOY                  ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# -------------------------------------------------------
# Step 1: Kill ALL old bot processes
# -------------------------------------------------------
echo ">>> [1/6] Stopping all bot processes..."
BOT_PIDS=$(pgrep -f smart_pump_reversal_bot.py 2>/dev/null || true)
if [ -n "$BOT_PIDS" ]; then
    echo "    Found PIDs: $BOT_PIDS"
    kill $BOT_PIDS 2>/dev/null || true
    sleep 4
    # Force kill if still running
    STILL_RUNNING=$(pgrep -f smart_pump_reversal_bot.py 2>/dev/null || true)
    if [ -n "$STILL_RUNNING" ]; then
        echo "    Force killing: $STILL_RUNNING"
        kill -9 $STILL_RUNNING 2>/dev/null || true
        sleep 2
    fi
    echo "    ✓ Bot stopped"
else
    echo "    No bot processes found (already stopped)"
fi

# -------------------------------------------------------
# Step 2: Pull latest code
# -------------------------------------------------------
echo ""
echo ">>> [2/6] Pulling latest code from branch: $BRANCH..."
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH"
echo "    ✓ Code updated — $(git log --oneline -1)"

# -------------------------------------------------------
# Step 3: Validate / keep live .env
# -------------------------------------------------------
echo ""
echo ">>> [3/6] Validating live .env..."
BACKUP_NAME=".env.backup_$(date +%Y%m%d_%H%M%S)"
if [ -f .env ]; then
    cp .env "$BACKUP_NAME"
    echo "    Old .env backed up to: $BACKUP_NAME"
fi

if [ -n "$SERVER_ENV_SOURCE" ]; then
    cp "$SERVER_ENV_SOURCE" .env
    echo "    ✓ .env replaced from SERVER_ENV_SOURCE=$SERVER_ENV_SOURCE"
elif [ -f .env ]; then
    echo "    ✓ Existing .env kept in place (default safe mode)"
else
    echo "    ✗ .env is missing and no SERVER_ENV_SOURCE was provided."
    echo "      Create /root/by-bot/.env manually or pass SERVER_ENV_SOURCE=/path/to/env"
    exit 1
fi

# Show what's active
echo ""
echo "    Active strategies:"
grep "^ENABLE_.*=1" .env | sed 's/^/      /'
echo ""
echo "    Key settings:"
grep -E "^ASC1_SYMBOL|^ARF1_SYMBOL|^ASC1_CONFIRM|^SLOPED_RISK|^FLAT_RISK" .env | sed 's/^/      /'

# -------------------------------------------------------
# Step 4: Clean stale runtime state
# -------------------------------------------------------
echo ""
echo ">>> [4/6] Cleaning stale runtime state..."
# Remove any lock files or stale state
find "$BOT_DIR/runtime" -name "*.pid" -delete 2>/dev/null || true
find "$BOT_DIR/runtime" -name "*.lock" -delete 2>/dev/null || true
# Remove any autoresearch processes that might be hogging resources
RESEARCH_PIDS=$(pgrep -f "run_strategy_autoresearch\|run_portfolio" 2>/dev/null || true)
if [ -n "$RESEARCH_PIDS" ]; then
    echo "    Stopping background research processes: $RESEARCH_PIDS"
    kill $RESEARCH_PIDS 2>/dev/null || true
    sleep 2
fi
echo "    ✓ Runtime state cleaned"

# -------------------------------------------------------
# Step 5: Verify Python dependencies
# -------------------------------------------------------
echo ""
echo ">>> [5/6] Checking Python setup..."
PYTHON_BIN=$(which python3)
echo "    Python: $PYTHON_BIN ($(python3 --version))"

# Quick syntax check on the main bot file
python3 -c "import py_compile; py_compile.compile('smart_pump_reversal_bot.py', doraise=True)" && \
    echo "    ✓ smart_pump_reversal_bot.py — syntax OK" || \
    { echo "    ✗ SYNTAX ERROR in bot file — aborting!"; exit 1; }

python3 -c "import py_compile; py_compile.compile('strategies/flat_resistance_fade_live.py', doraise=True)" && \
    echo "    ✓ flat_resistance_fade_live.py — syntax OK" || \
    { echo "    ✗ SYNTAX ERROR in strategy file — aborting!"; exit 1; }

python3 -c "import py_compile; py_compile.compile('strategies/alt_sloped_channel_v1.py', doraise=True)" && \
    echo "    ✓ alt_sloped_channel_v1.py — syntax OK" || \
    { echo "    ✗ SYNTAX ERROR in strategy file — aborting!"; exit 1; }

# -------------------------------------------------------
# Step 6: Start bot fresh
# -------------------------------------------------------
echo ""
echo ">>> [6/6] Starting bot..."
LOGFILE="$LOG_DIR/bot_$(date +%Y%m%d_%H%M%S).log"
nohup python3 smart_pump_reversal_bot.py > "$LOGFILE" 2>&1 &
BOT_PID=$!
echo "    PID: $BOT_PID"
echo "    Log: $LOGFILE"

# Wait a moment and verify it started
sleep 5
if kill -0 $BOT_PID 2>/dev/null; then
    echo "    ✓ Bot is running!"
else
    echo "    ✗ Bot crashed on startup! Check log:"
    tail -30 "$LOGFILE"
    exit 1
fi

# -------------------------------------------------------
# Done — show last log lines
# -------------------------------------------------------
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   DEPLOY COMPLETE                            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Tail log with:"
echo "  tail -f $LOGFILE"
echo ""
echo "Check bot status (Telegram /status or):"
echo "  grep -i 'engine\|ERROR\|FLAT\|SLOPED' $LOGFILE | head -30"
echo ""
sleep 3
echo "=== First log lines ==="
grep -i "engine\|init\|start\|ERROR\|strategy" "$LOGFILE" 2>/dev/null | head -20 || tail -20 "$LOGFILE"
