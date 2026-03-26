#!/bin/bash
# ===================================================================
# deploy_session10.sh — Деплой сессии 10
#
# Запускай с локального терминала:
#   bash scripts/deploy_session10.sh
#
# Что деплоится:
#   1. TG bot: упрощённые кнопки (6 вместо 10), новое /help меню
#   2. DEEPSEEK_API_KEY — добавляется в server .env
#   3. DEEPSEEK_ENABLE=1 проверяется и включается
#   4. strategies/breakdown_live.py — LIVE интеграция breakdown shorts
# ===================================================================
set -e
SSH_KEY="${SSH_KEY:-$HOME/.ssh/by-bot}"
SERVER="root@64.226.73.119"
LOCAL="$(cd "$(dirname "$0")/.." && pwd)"

echo "╔══════════════════════════════════════════╗"
echo "║        Session 10 Deploy to Server       ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 0. Check SSH key ─────────────────────────────────────────────
if [ ! -f "$SSH_KEY" ]; then
    echo "❌ SSH key not found: $SSH_KEY"
    echo "   Укажи ключ: SSH_KEY=~/.ssh/id_rsa bash scripts/deploy_session10.sh"
    exit 1
fi

echo "✅ SSH key: $SSH_KEY"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$SERVER" "echo '✅ SSH connection OK'" || {
    echo "❌ SSH failed. Попробуй: ssh -i $SSH_KEY root@64.226.73.119"
    exit 1
}

# ── 1. Syntax check ──────────────────────────────────────────────
echo ""
echo "[1/5] Syntax check..."
python3 -m py_compile "$LOCAL/smart_pump_reversal_bot.py" && echo "  ✅ smart_pump_reversal_bot.py"
python3 -m py_compile "$LOCAL/strategies/breakdown_live.py" && echo "  ✅ strategies/breakdown_live.py"
python3 -m py_compile "$LOCAL/bot/deepseek_overlay.py" && echo "  ✅ bot/deepseek_overlay.py"

# ── 2. Copy bot files ─────────────────────────────────────────────
echo ""
echo "[2/5] Copying bot files..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    "$LOCAL/smart_pump_reversal_bot.py" \
    "$SERVER:/root/by-bot/"
echo "  ✅ smart_pump_reversal_bot.py"
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    "$LOCAL/strategies/breakdown_live.py" \
    "$SERVER:/root/by-bot/strategies/"
echo "  ✅ strategies/breakdown_live.py"
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    "$LOCAL/bot/deepseek_overlay.py" \
    "$SERVER:/root/by-bot/bot/"
echo "  ✅ bot/deepseek_overlay.py"

# ── 3. Patch .env with DeepSeek API key ─────────────────────────
echo ""
echo "[3/5] Patching .env (DeepSeek)..."
# Read API key from local server_clean.env
DSKEY=$(grep "^DEEPSEEK_API_KEY=" "$LOCAL/configs/server_clean.env" | cut -d= -f2- | tr -d '[:space:]')
if [ -z "$DSKEY" ]; then
    echo "  ⚠️  DEEPSEEK_API_KEY not found in server_clean.env, skipping"
else
    echo "  Found DEEPSEEK_API_KEY in server_clean.env"
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" bash << REMOTE_EOF
ENV="/root/by-bot/.env"

patch_or_add() {
    local key="\$1" val="\$2"
    if grep -q "^\${key}=" "\$ENV"; then
        sed -i "s|^\${key}=.*|\${key}=\${val}|" "\$ENV"
        echo "  updated: \${key}"
    else
        echo "" >> "\$ENV"
        echo "\${key}=\${val}" >> "\$ENV"
        echo "  added:   \${key}"
    fi
}

patch_or_add "DEEPSEEK_API_KEY" "$DSKEY"
patch_or_add "DEEPSEEK_ENABLE" "1"
patch_or_add "DEEPSEEK_MODEL" "deepseek-chat"
patch_or_add "DEEPSEEK_TIMEOUT_SEC" "20"
patch_or_add "DEEPSEEK_HISTORY_MAX_MESSAGES" "16"

echo "--- Current DeepSeek config ---"
grep "DEEPSEEK" "\$ENV"
REMOTE_EOF
fi

# ── 3b. Patch .env with expansion results ────────────────────────
echo ""
echo "[3b/5] Patching .env (expansion best settings)..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" bash << 'EXPAND_EOF'
ENV="/root/by-bot/.env"

patch_or_add() {
    local key="$1" val="$2"
    if grep -q "^${key}=" "$ENV"; then
        sed -i "s|^${key}=.*|${key}=${val}|" "$ENV"
        echo "  updated: ${key}=${val}"
    else
        echo "" >> "$ENV"
        echo "${key}=${val}" >> "$ENV"
        echo "  added:   ${key}=${val}"
    fi
}

# ASC1 expansion: ATOM+LINK+DOT best (asc1_expansion_v1, 2026-03-26)
patch_or_add "ASC1_SYMBOL_ALLOWLIST" "ATOMUSDT,LINKUSDT,DOTUSDT"

# Breakdown expansion: 6 coins best (breakdown_expansion_v1, 2026-03-26)
patch_or_add "BREAKDOWN_SYMBOL_ALLOWLIST" "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ATOMUSDT,LTCUSDT"

echo "--- Updated strategy allowlists ---"
grep -E "^(ASC1_SYMBOL_ALLOWLIST|BREAKDOWN_SYMBOL_ALLOWLIST)=" "$ENV"
EXPAND_EOF

# ── 4. Restart bot ───────────────────────────────────────────────
echo ""
echo "[4/6] Verifying breakdown strategy on server..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" \
    "python3 -c 'from strategies.breakdown_live import BreakdownLiveEngine; print(\"  ✅ breakdown_live import OK\")' 2>&1 || echo '  ❌ import failed'"

echo ""
echo "[5/6] Restarting bybot service..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" \
    "systemctl restart bybot && sleep 3 && systemctl status bybot --no-pager | head -15"

echo ""
echo "[6/6] Done."
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║           Deploy complete! ✅             ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Проверь в Telegram: /help"
echo "Проверь DeepSeek: /ai привет"
echo "Проверь breakdown: в /status должно быть breakdown=True"
