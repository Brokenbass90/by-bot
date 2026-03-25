#!/bin/bash
# ===================================================================
# deploy_all_latest.sh — пушит ВСЕ последние изменения на сервер
# Запускай с локального терминала: bash scripts/deploy_all_latest.sh
# ===================================================================
set -e
SSH_KEY="${SSH_KEY:-~/.ssh/by-bot}"
SERVER="root@64.226.73.119"
REMOTE_DIR="/root/by-bot"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Deploy all latest changes to $SERVER ==="
echo ""

# --- 1. Ключевые файлы бота ---
echo "[1/5] Bot core files..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/bot/deepseek_overlay.py" \
  "$LOCAL_DIR/bot/deepseek_autoresearch_agent.py" \
  "$LOCAL_DIR/smart_pump_reversal_bot.py" \
  "$SERVER:$REMOTE_DIR/bot/" 2>/dev/null || \
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/bot/deepseek_overlay.py" \
  "$LOCAL_DIR/bot/deepseek_autoresearch_agent.py" \
  "$SERVER:$REMOTE_DIR/bot/"
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/smart_pump_reversal_bot.py" \
  "$SERVER:$REMOTE_DIR/"

# --- 2. Стратегии ---
echo "[2/5] Strategies..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/strategies/alt_sloped_channel_v1.py" \
  "$LOCAL_DIR/strategies/alt_resistance_fade_v1.py" \
  "$LOCAL_DIR/strategies/alt_inplay_breakdown_v1.py" \
  "$LOCAL_DIR/strategies/inplay_breakout.py" \
  "$LOCAL_DIR/strategies/btc_eth_midterm_pullback.py" \
  "$SERVER:$REMOTE_DIR/strategies/"

# --- 3. Конфиги autoresearch ---
echo "[3/5] Autoresearch configs..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "mkdir -p $REMOTE_DIR/configs/autoresearch"
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/configs/autoresearch/asc1_trailing_v1.json" \
  "$LOCAL_DIR/configs/autoresearch/arf1_trailing_v1.json" \
  "$LOCAL_DIR/configs/autoresearch/triple_screen_elder_friend_v11.json" \
  "$LOCAL_DIR/configs/autoresearch/flat_arf1_expansion_v2.json" \
  "$SERVER:$REMOTE_DIR/configs/autoresearch/"

# --- 4. Env: добавить TG_ADMIN_USER_ID если не установлен ---
echo "[4/5] Env patch..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "
  # Создать data/ директорию
  mkdir -p $REMOTE_DIR/data

  # Добавить TG_ADMIN_USER_ID если нет
  if ! grep -q 'TG_ADMIN_USER_ID' $REMOTE_DIR/.env; then
    echo '' >> $REMOTE_DIR/.env
    echo 'TG_ADMIN_USER_ID=319077869' >> $REMOTE_DIR/.env
    echo 'Added TG_ADMIN_USER_ID'
  else
    echo 'TG_ADMIN_USER_ID already set'
  fi

  # Перенести старую /tmp/ историю DeepSeek если есть
  [ -f /tmp/bybot_deepseek_chat.json ] && cp /tmp/bybot_deepseek_chat.json $REMOTE_DIR/data/deepseek_chat.json && echo 'Migrated chat history' || true
"

# --- 5. Syntax check + restart ---
echo "[5/5] Syntax check & restart..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "
  cd $REMOTE_DIR
  python3 -m py_compile bot/deepseek_overlay.py && echo 'deepseek_overlay: OK'
  python3 -m py_compile bot/deepseek_autoresearch_agent.py && echo 'deepseek_autoresearch_agent: OK'
  python3 -m py_compile smart_pump_reversal_bot.py && echo 'smart_pump_reversal_bot: OK'
  python3 -m py_compile strategies/alt_sloped_channel_v1.py && echo 'asc1: OK'
  python3 -m py_compile strategies/alt_resistance_fade_v1.py && echo 'arf1: OK'
  echo ''
  systemctl restart bybot
  sleep 3
  systemctl status bybot --no-pager | head -6
"

echo ""
echo "=== ДЕПЛОЙ ЗАВЕРШЁН ==="
echo ""
echo "Что развёрнуто:"
echo "  DeepSeek partner mode: знает архитектуру бота, история в data/"
echo "  ASC1: новый ASC1_TRAIL_ATR_MULT=0 (trailing выключен — бэктест показал ухудшение)"
echo "  ARF1: новый ARF1_TRAIL_ATR_MULT=0 (trailing выключен — бэктест показал ухудшение)"
echo "  TG_ADMIN_USER_ID: защита команд бота"
echo ""
echo "Запустить trailing autoresearch на сервере (для проверки граничных значений):"
echo "  ssh root@64.226.73.119 'cd /root/by-bot && BACKTEST_CACHE_ONLY=1 python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/asc1_trailing_v1.json > /tmp/trail_asc1.log 2>&1 &'"
