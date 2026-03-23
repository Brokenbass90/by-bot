#!/bin/bash
# Deploy DeepSeek Partner Mode + Trailing Stop support to server
# Changes:
#   - deepseek_overlay.py: rich system prompt (full architecture context), persistent history
#     in /root/by-bot/data/, history=16 messages, timeout=20s
#   - alt_sloped_channel_v1.py: ASC1_TRAIL_ATR_MULT param (default 0 = off)
#   - alt_resistance_fade_v1.py: ARF1_TRAIL_ATR_MULT param (default 0 = off)
#
# Run from your local terminal: bash scripts/deploy_deepseek_partner.sh

set -e
SSH_KEY="${SSH_KEY:-~/.ssh/by-bot}"
SERVER="root@64.226.73.119"
REMOTE_DIR="/root/by-bot"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Deploy: DeepSeek Partner Mode + Trailing Stop Support ==="
echo "Local: $LOCAL_DIR"
echo "Remote: $SERVER:$REMOTE_DIR"
echo ""

# 1. Copy changed files
echo "Copying bot/deepseek_overlay.py..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/bot/deepseek_overlay.py" \
  "$SERVER:$REMOTE_DIR/bot/deepseek_overlay.py"

echo "Copying strategies/alt_sloped_channel_v1.py..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/strategies/alt_sloped_channel_v1.py" \
  "$SERVER:$REMOTE_DIR/strategies/alt_sloped_channel_v1.py"

echo "Copying strategies/alt_resistance_fade_v1.py..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/strategies/alt_resistance_fade_v1.py" \
  "$SERVER:$REMOTE_DIR/strategies/alt_resistance_fade_v1.py"

# 2. Create data/ directory for persistent storage
echo ""
echo "Creating /root/by-bot/data/ directory..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "
  mkdir -p $REMOTE_DIR/data
  echo 'data/ directory ready'

  # Migrate old /tmp/ history to persistent location (if exists)
  if [ -f /tmp/bybot_deepseek_chat.json ]; then
    cp /tmp/bybot_deepseek_chat.json $REMOTE_DIR/data/deepseek_chat.json
    echo 'Migrated chat history from /tmp/ to data/'
  fi
  if [ -f /tmp/bybot_deepseek_audit.jsonl ]; then
    cp /tmp/bybot_deepseek_audit.jsonl $REMOTE_DIR/data/deepseek_audit.jsonl
    echo 'Migrated audit log from /tmp/ to data/'
  fi
"

# 3. Syntax checks on server
echo ""
echo "Checking syntax on server..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "
  cd $REMOTE_DIR
  python3 -m py_compile bot/deepseek_overlay.py && echo 'deepseek_overlay: OK'
  python3 -m py_compile strategies/alt_sloped_channel_v1.py && echo 'alt_sloped_channel_v1: OK'
  python3 -m py_compile strategies/alt_resistance_fade_v1.py && echo 'alt_resistance_fade_v1: OK'
"

# 4. Restart bot
echo ""
echo "Restarting bybot service..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "
  systemctl restart bybot
  sleep 3
  systemctl status bybot --no-pager | head -8
"

echo ""
echo "=== Deploy complete! ==="
echo ""
echo "What changed:"
echo "  DeepSeek (/ai) — теперь знает архитектуру бота: 5 стратегий, параметры, trailing stop"
echo "  DeepSeek история — сохраняется в /root/by-bot/data/ (не теряется при перезапуске)"
echo "  DeepSeek — помнит последние 16 сообщений (было 8), таймаут 20s (было 8s)"
echo "  ASC1 — новый параметр ASC1_TRAIL_ATR_MULT (по умолчанию 0 = выкл)"
echo "  ARF1 — новый параметр ARF1_TRAIL_ATR_MULT (по умолчанию 0 = выкл)"
echo ""
echo "Trailing stop (пока выкл): чтобы включить на ASC1 на сервере:"
echo "  ssh root@64.226.73.119 \"sed -i '/ASC1_/s/$//' /root/by-bot/.env\" # нет готового one-liner"
echo "  Лучше: дождись результатов autoresearch asc1_trailing_v1 — найдёт лучший мультипликатор"
echo ""
echo "Autoresearch для trailing (запусти локально на сервере backtests):"
echo "  python scripts/run_strategy_autoresearch.py --spec configs/autoresearch/asc1_trailing_v1.json"
echo "  python scripts/run_strategy_autoresearch.py --spec configs/autoresearch/arf1_trailing_v1.json"
