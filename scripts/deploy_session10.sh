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
echo "[1/4] Syntax check..."
python3 -m py_compile "$LOCAL/smart_pump_reversal_bot.py" && echo "  ✅ smart_pump_reversal_bot.py"

# ── 2. Copy main bot file ────────────────────────────────────────
echo ""
echo "[2/4] Copying main bot file..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    "$LOCAL/smart_pump_reversal_bot.py" \
    "$SERVER:/root/by-bot/"
echo "  ✅ smart_pump_reversal_bot.py"

# ── 3. Patch .env with DeepSeek API key ─────────────────────────
echo ""
echo "[3/4] Patching .env (DeepSeek)..."
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

# ── 4. Restart bot ───────────────────────────────────────────────
echo ""
echo "[4/4] Restarting bybot service..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" \
    "systemctl restart bybot && sleep 3 && systemctl status bybot --no-pager | head -15"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║           Deploy complete! ✅             ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Проверь в Telegram: /help"
echo "Проверь DeepSeek: /ai привет"
