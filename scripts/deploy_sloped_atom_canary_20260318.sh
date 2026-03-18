#!/usr/bin/env bash
set -euo pipefail

BRANCH="codex/dynamic-symbol-filters"
SERVER_IP="64.226.73.119"
SERVER_USER="root"
BOT_DIR="/root/by-bot"
SSH_KEY="$HOME/.ssh/by-bot"
GITHUB_USER="Brokenbass90"
GITHUB_REPO="by-bot"
TOKEN_FILE="$HOME/.by-bot-github-token"

if [ -f "$TOKEN_FILE" ]; then
    GITHUB_TOKEN=$(cat "$TOKEN_FILE")
    echo "Using saved GitHub token from $TOKEN_FILE"
else
    echo ""
    echo "GitHub token not found. Create one at:"
    echo "https://github.com/settings/tokens"
    echo "(Fine-grained -> only 'by-bot' repo -> Contents: Read+Write)"
    echo ""
    read -r -p "Paste your GitHub token: " GITHUB_TOKEN
    if [ -z "$GITHUB_TOKEN" ]; then
        echo "No token provided. Aborting."
        exit 1
    fi
    echo "$GITHUB_TOKEN" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
    echo "Token saved to $TOKEN_FILE"
fi

if [ ! -f "$SSH_KEY" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
    for K in "$PROJECT_ROOT/.ssh/by-bot" "$HOME/.ssh/id_ed25519" "$HOME/.ssh/id_rsa"; do
        if [ -f "$K" ]; then
            SSH_KEY="$K"
            break
        fi
    done
fi

SSH_CMD="ssh -i $SSH_KEY -o StrictHostKeyChecking=no"
HTTPS_URL="https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${GITHUB_REPO}.git"

echo ""
echo "=============================================="
echo "  DEPLOY SLOPED ATOM CANARY - $(date '+%Y-%m-%d %H:%M:%S')"
echo "  branch=$BRANCH server=$SERVER_IP"
echo "=============================================="

echo ""
echo "[1/4] Push branch to GitHub..."
git push "$HTTPS_URL" "$BRANCH"
echo "OK: GitHub updated"

echo ""
echo "[2/4] Pull branch on server..."
$SSH_CMD "$SERVER_USER@$SERVER_IP" bash <<ENDSSH
set -e
cd $BOT_DIR
git fetch origin $BRANCH
git checkout $BRANCH 2>/dev/null || true
git pull origin $BRANCH
git log --oneline -3
ENDSSH

echo ""
echo "[3/4] Apply ATOM sloped canary env..."
$SSH_CMD "$SERVER_USER@$SERVER_IP" bash <<'ENDSSH'
set -e
cd /root/by-bot

upsert_env() {
    key="$1"
    value="$2"
    if grep -q "^${key}=" .env 2>/dev/null; then
        sed -i "s#^${key}=.*#${key}=${value}#" .env
    else
        echo "${key}=${value}" >> .env
    fi
}

upsert_env BREAKOUT_QUALITY_MIN_SCORE 0.0
upsert_env ENABLE_SLOPED_TRADING 1
upsert_env ENABLE_TS132_TRADING 0
upsert_env SLOPED_TRY_EVERY_SEC 60
upsert_env SLOPED_RISK_MULT 0.10
upsert_env SLOPED_MAX_OPEN_TRADES 1
upsert_env ASC1_ALLOW_LONGS 0
upsert_env ASC1_ALLOW_SHORTS 1
upsert_env ASC1_SYMBOL_ALLOWLIST ATOMUSDT
upsert_env ASC1_MAX_ABS_SLOPE_PCT 2.0
upsert_env ASC1_MIN_RANGE_R2 0.25
upsert_env ASC1_SHORT_MAX_NEAR_UPPER_BARS 2
upsert_env ASC1_SHORT_MIN_REJECT_DEPTH_ATR 0.75
upsert_env ASC1_SHORT_MIN_RSI 60
upsert_env ASC1_SHORT_NEAR_UPPER_ATR 0.15
upsert_env ASC1_SHORT_MIN_REJECT_VOL_MULT 0.0
upsert_env ASC1_TP1_FRAC 0.45
upsert_env ASC1_TP2_BUFFER_PCT 0.40
upsert_env ASC1_TIME_STOP_BARS_5M 480

echo "Current sloped canary flags:"
grep -E '^(BREAKOUT_QUALITY_MIN_SCORE|ENABLE_SLOPED_TRADING|ENABLE_TS132_TRADING|SLOPED_|ASC1_)=' .env | sort
ENDSSH

echo ""
echo "[4/4] Restart bot..."
$SSH_CMD "$SERVER_USER@$SERVER_IP" bash <<'ENDSSH'
set -e
cd /root/by-bot

if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet bot 2>/dev/null; then
    systemctl restart bot
elif screen -list 2>/dev/null | grep -q "bot"; then
    screen -S bot -X quit 2>/dev/null || true
    sleep 2
    if [ -f scripts/start_bot.sh ]; then
        screen -dmS bot bash scripts/start_bot.sh
    else
        screen -dmS bot python3 smart_pump_reversal_bot.py
    fi
elif [ -f scripts/start_bot.sh ]; then
    screen -dmS bot bash scripts/start_bot.sh
else
    echo "WARNING: restart must be done manually"
fi
ENDSSH

echo ""
echo "=============================================="
echo "  Sloped ATOM canary deploy complete"
echo "  Note: this does NOT change global risk/max positions"
echo "=============================================="
