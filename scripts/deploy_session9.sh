#!/bin/bash
# ===================================================================
# deploy_session9.sh — Финальный деплой сессий 8-9
#
# Запускай с локального терминала:
#   bash scripts/deploy_session9.sh
#
# Что деплоится:
#   1. DeepSeek partner mode (deepseek_overlay.py)
#   2. DeepSeek audit/code команды (deepseek_autoresearch_agent.py)
#   3. TG security: TG_ADMIN_USER_ID
#   4. BREAKOUT quality filter bug fix: BREAKOUT_QUALITY_MIN_SCORE=0.48
#   5. BREAKOUT_MAX_CHASE_PCT=0.11 (было 0.14)
#   6. Breakdown shorts ВКЛЮЧЁН на BTC+ETH+SOL
#   7. ARF1 расширен до 6 монет (+ADA+BCH): +9% net, 0 red months
#   8. ASC1/ARF1: trail params (=0, trailing не помогает mean-reversion)
# ===================================================================
set -e
SSH_KEY="${SSH_KEY:-~/.ssh/by-bot}"
SERVER="root@64.226.73.119"
REMOTE="$SERVER:/root/by-bot"
LOCAL="$(cd "$(dirname "$0")/.." && pwd)"

echo "╔══════════════════════════════════════════╗"
echo "║        Session 9 Deploy to Server        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Bot core files ──────────────────────────────────────────────
echo "[1/6] Copying bot files..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    "$LOCAL/bot/deepseek_overlay.py" \
    "$LOCAL/bot/deepseek_autoresearch_agent.py" \
    "$SERVER:/root/by-bot/bot/"
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    "$LOCAL/smart_pump_reversal_bot.py" \
    "$SERVER:/root/by-bot/"

# ── 2. Strategies ─────────────────────────────────────────────────
echo "[2/6] Copying strategies..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    "$LOCAL/strategies/alt_sloped_channel_v1.py" \
    "$LOCAL/strategies/alt_resistance_fade_v1.py" \
    "$LOCAL/strategies/alt_inplay_breakdown_v1.py" \
    "$LOCAL/strategies/inplay_breakout.py" \
    "$LOCAL/strategies/btc_eth_midterm_pullback.py" \
    "$SERVER:/root/by-bot/strategies/"

# ── 3. Autoresearch configs ────────────────────────────────────────
echo "[3/6] Copying autoresearch configs..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" \
    "mkdir -p /root/by-bot/configs/autoresearch /root/by-bot/data"
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    "$LOCAL/configs/autoresearch/triple_screen_elder_friend_v11.json" \
    "$LOCAL/configs/autoresearch/flat_arf1_expansion_v2.json" \
    "$LOCAL/configs/autoresearch/asc1_trailing_v1.json" \
    "$LOCAL/configs/autoresearch/arf1_trailing_v1.json" \
    "$SERVER:/root/by-bot/configs/autoresearch/"

# ── 4. Patch .env ─────────────────────────────────────────────────
echo "[4/6] Patching .env..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" bash << 'REMOTE_EOF'
ENV="/root/by-bot/.env"
DATA="/root/by-bot/data"
mkdir -p "$DATA"

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

echo "--- Security ---"
patch_or_add "TG_ADMIN_USER_ID" "319077869"

echo "--- Breakout quality filter bug fix ---"
patch_or_add "BREAKOUT_QUALITY_MIN_SCORE" "0.48"
patch_or_add "BT_BREAKOUT_QUALITY_MIN_SCORE" "0.48"
patch_or_add "BT_BREAKOUT_QUALITY_ENABLE" "1"
patch_or_add "BREAKOUT_MAX_CHASE_PCT" "0.11"

echo "--- Breakdown ENABLE ---"
patch_or_add "ENABLE_BREAKDOWN_TRADING" "1"
patch_or_add "BREAKDOWN_SYMBOL_ALLOWLIST" "BTCUSDT,ETHUSDT,SOLUSDT"
patch_or_add "BREAKDOWN_ALLOW_LONGS" "0"
patch_or_add "BREAKDOWN_ALLOW_SHORTS" "1"
patch_or_add "BREAKDOWN_REGIME_MODE" "off"
patch_or_add "BREAKDOWN_LOOKBACK_H" "48"
patch_or_add "BREAKDOWN_RR" "2.0"
patch_or_add "BREAKDOWN_SL_ATR" "1.8"
patch_or_add "BREAKDOWN_MAX_DIST_ATR" "2.0"
patch_or_add "BREAKDOWN_RISK_MULT" "0.10"
patch_or_add "BREAKDOWN_MAX_OPEN_TRADES" "1"

echo "--- ARF1: expand to 6 coins ---"
patch_or_add "ARF1_SYMBOL_ALLOWLIST" "LINKUSDT,LTCUSDT,SUIUSDT,DOTUSDT,ADAUSDT,BCHUSDT"

echo "--- DeepSeek improvements ---"
patch_or_add "DEEPSEEK_TIMEOUT_SEC" "20"
patch_or_add "DEEPSEEK_HISTORY_MAX_MESSAGES" "16"

echo "--- Migrate DeepSeek history if needed ---"
[ -f /tmp/bybot_deepseek_chat.json ] && \
    cp /tmp/bybot_deepseek_chat.json "$DATA/deepseek_chat.json" && \
    echo "  migrated: chat history from /tmp/ to data/" || true

echo ""
echo "Final key values:"
grep -E "^(BREAKOUT_QUALITY_MIN_SCORE|BT_BREAKOUT_QUALITY_MIN_SCORE|BREAKOUT_MAX_CHASE_PCT|ENABLE_BREAKDOWN_TRADING|BREAKDOWN_SYMBOL_ALLOWLIST|ARF1_SYMBOL_ALLOWLIST)" "$ENV"
REMOTE_EOF

# ── 5. Syntax checks ──────────────────────────────────────────────
echo ""
echo "[5/6] Syntax checks..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" bash << 'REMOTE_EOF'
cd /root/by-bot
python3 -m py_compile bot/deepseek_overlay.py           && echo "  ✅ deepseek_overlay"
python3 -m py_compile bot/deepseek_autoresearch_agent.py && echo "  ✅ deepseek_autoresearch_agent"
python3 -m py_compile smart_pump_reversal_bot.py         && echo "  ✅ smart_pump_reversal_bot"
python3 -m py_compile strategies/alt_sloped_channel_v1.py && echo "  ✅ alt_sloped_channel_v1"
python3 -m py_compile strategies/alt_resistance_fade_v1.py && echo "  ✅ alt_resistance_fade_v1"
python3 -m py_compile strategies/alt_inplay_breakdown_v1.py && echo "  ✅ alt_inplay_breakdown_v1"
python3 -m py_compile strategies/inplay_breakout.py      && echo "  ✅ inplay_breakout"
REMOTE_EOF

# ── 6. Restart ────────────────────────────────────────────────────
echo ""
echo "[6/6] Restarting bybot..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" \
    "systemctl restart bybot && sleep 4 && systemctl status bybot --no-pager | head -8"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║            DEPLOY COMPLETE ✅            ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Deployed:"
echo "  ✅ DeepSeek partner mode — знает архитектуру, история в /root/by-bot/data/"
echo "  ✅ BREAKOUT_QUALITY_MIN_SCORE=0.48 (КРИТИЧЕСКИЙ БАГ-ФИКС)"
echo "  ✅ BREAKOUT_MAX_CHASE_PCT=0.11"
echo "  ✅ Breakdown shorts ВКЛЮЧЁН (BTC+ETH+SOL)"
echo "     Бэктест: +36% net, PF 1.92, WR 54.7%, 0 красных месяцев"
echo "  ✅ ARF1: 6 монет (добавлены ADA+BCH)"
echo "     Бэктест: +37.48% vs +28.60%, 0 красных месяцев"
echo ""
echo "Мониторинг через Telegram:"
echo "  /status   — живые позиции"
echo "  /health   — здоровье за 30 дней"
echo "  /ai что изменилось сегодня?  — спросить DeepSeek"
