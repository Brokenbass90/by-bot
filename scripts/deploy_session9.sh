#!/bin/bash
# ===================================================================
# deploy_session9.sh — Деплой всех улучшений сессии 9
#
# Запускай с локального терминала:
#   bash scripts/deploy_session9.sh
#
# Что деплоится:
#   1. DeepSeek partner mode — знает архитектуру, история в data/, 16 msg, timeout 20s
#   2. BREAKOUT_QUALITY_MIN_SCORE=0.48 — баг-фикс (live filter был 0.0)
#   3. BREAKOUT_MAX_CHASE_PCT=0.11 (было 0.14)
#   4. ASC1 + ARF1: новые trail params (по умолч. 0 = выкл, trail не помогает)
#   5. Обновлённый server env с лучшими параметрами
# ===================================================================
set -e
SSH_KEY="${SSH_KEY:-~/.ssh/by-bot}"
SERVER="root@64.226.73.119"
REMOTE_DIR="/root/by-bot"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Session 9 Deploy ==="
echo ""

# 1. Файлы бота
echo "[1/6] Bot core..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/bot/deepseek_overlay.py" \
  "$LOCAL_DIR/bot/deepseek_autoresearch_agent.py" \
  "$SERVER:$REMOTE_DIR/bot/"
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/smart_pump_reversal_bot.py" \
  "$SERVER:$REMOTE_DIR/"

# 2. Стратегии
echo "[2/6] Strategies..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/strategies/alt_sloped_channel_v1.py" \
  "$LOCAL_DIR/strategies/alt_resistance_fade_v1.py" \
  "$LOCAL_DIR/strategies/alt_inplay_breakdown_v1.py" \
  "$LOCAL_DIR/strategies/inplay_breakout.py" \
  "$LOCAL_DIR/strategies/btc_eth_midterm_pullback.py" \
  "$SERVER:$REMOTE_DIR/strategies/"

# 3. Autoresearch configs
echo "[3/6] Autoresearch configs..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/configs/autoresearch/asc1_trailing_v1.json" \
  "$LOCAL_DIR/configs/autoresearch/arf1_trailing_v1.json" \
  "$LOCAL_DIR/configs/autoresearch/triple_screen_elder_friend_v11.json" \
  "$LOCAL_DIR/configs/autoresearch/flat_arf1_expansion_v2.json" \
  "$SERVER:$REMOTE_DIR/configs/autoresearch/"

# 4. Патч .env с лучшими параметрами
echo "[4/6] Env patch..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "
  mkdir -p $REMOTE_DIR/data

  # Перенести историю DeepSeek если есть
  [ -f /tmp/bybot_deepseek_chat.json ] && cp /tmp/bybot_deepseek_chat.json $REMOTE_DIR/data/deepseek_chat.json && echo 'Migrated chat history' || true

  # TG_ADMIN_USER_ID
  grep -q 'TG_ADMIN_USER_ID' $REMOTE_DIR/.env || echo 'TG_ADMIN_USER_ID=319077869' >> $REMOTE_DIR/.env

  # BREAKOUT quality filter BUG FIX: добавить BREAKOUT_QUALITY_MIN_SCORE=0.48
  if ! grep -q '^BREAKOUT_QUALITY_MIN_SCORE=' $REMOTE_DIR/.env; then
    sed -i '/^BT_BREAKOUT_QUALITY_MIN_SCORE/a BREAKOUT_QUALITY_MIN_SCORE=0.48' $REMOTE_DIR/.env
    echo 'Added BREAKOUT_QUALITY_MIN_SCORE=0.48 (bug fix: live filter was 0.0)'
  else
    sed -i 's/^BREAKOUT_QUALITY_MIN_SCORE=.*/BREAKOUT_QUALITY_MIN_SCORE=0.48/' $REMOTE_DIR/.env
    echo 'Updated BREAKOUT_QUALITY_MIN_SCORE=0.48'
  fi

  # Update BT_BREAKOUT_QUALITY_MIN_SCORE 0.54 → 0.48
  sed -i 's/^BT_BREAKOUT_QUALITY_MIN_SCORE=.*/BT_BREAKOUT_QUALITY_MIN_SCORE=0.48/' $REMOTE_DIR/.env

  # Update chase 0.14 → 0.11
  sed -i 's/^BREAKOUT_MAX_CHASE_PCT=.*/BREAKOUT_MAX_CHASE_PCT=0.11/' $REMOTE_DIR/.env

  # DeepSeek improvements
  sed -i 's/^DEEPSEEK_TIMEOUT_SEC=.*/DEEPSEEK_TIMEOUT_SEC=20/' $REMOTE_DIR/.env
  sed -i 's/^DEEPSEEK_HISTORY_MAX_MESSAGES=.*/DEEPSEEK_HISTORY_MAX_MESSAGES=16/' $REMOTE_DIR/.env

  echo 'Env patched'
  echo ''
  echo 'Current key breakout params:'
  grep 'BREAKOUT_QUALITY_MIN_SCORE\|BT_BREAKOUT_QUALITY_MIN_SCORE\|BREAKOUT_MAX_CHASE_PCT\|BREAKOUT_ALLOW_SHORTS' $REMOTE_DIR/.env
"

# 5. Syntax check
echo ""
echo "[5/6] Syntax check..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "
  cd $REMOTE_DIR
  python3 -m py_compile bot/deepseek_overlay.py && echo 'deepseek_overlay: OK'
  python3 -m py_compile bot/deepseek_autoresearch_agent.py && echo 'deepseek_autoresearch_agent: OK'
  python3 -m py_compile smart_pump_reversal_bot.py && echo 'smart_pump_reversal_bot: OK'
  python3 -m py_compile strategies/alt_sloped_channel_v1.py && echo 'asc1: OK'
  python3 -m py_compile strategies/alt_resistance_fade_v1.py && echo 'arf1: OK'
"

# 6. Restart
echo ""
echo "[6/6] Restart bybot..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "
  systemctl restart bybot
  sleep 4
  systemctl status bybot --no-pager | head -6
"

echo ""
echo "=== SESSION 9 DEPLOY COMPLETE ==="
echo ""
echo "Deployed fixes:"
echo "  ✅ DeepSeek partner mode: знает архитектуру, история в /root/by-bot/data/"
echo "  ✅ BREAKOUT_QUALITY_MIN_SCORE=0.48 — БАГ-ФИКС (live filter был отключён!)"
echo "  ✅ BREAKOUT_MAX_CHASE_PCT=0.11 (было 0.14, autoresearch r003)"
echo "  ✅ BT_BREAKOUT_QUALITY_MIN_SCORE=0.48 (было 0.54)"
echo "  ✅ ASC1 + ARF1: trail params (=0, trailing ухудшает mean-reversion)"
echo "  ✅ DeepSeek timeout 20s, history 16 messages"
echo ""
echo "Research findings (не деплоится автоматически, требует решения):"
echo "  📊 Breakdown shorts (BTC+ETH+SOL): +36% net, PF 1.92, WR 54.7%, 0 red months"
echo "     → Включить: bash scripts/enable_breakdown_shorts.sh"
echo ""
echo "  📊 ARF1 6 coins (+ADA+BCH): +37.48% vs +28.60% (4 coins), 0 red months"
echo "     → Включить: edit .env, set ARF1_SYMBOL_ALLOWLIST=LINKUSDT,LTCUSDT,SUIUSDT,DOTUSDT,ADAUSDT,BCHUSDT"
