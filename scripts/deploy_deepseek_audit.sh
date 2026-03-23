#!/bin/bash
# Deploy DeepSeek audit + TG security hardening to server
# Run from your local terminal: bash scripts/deploy_deepseek_audit.sh

set -e
SSH_KEY="${SSH_KEY:-~/.ssh/by-bot}"
SERVER="root@64.226.73.119"
REMOTE_DIR="/root/by-bot"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Deploy: DeepSeek Audit + TG Security ==="
echo "Local: $LOCAL_DIR"
echo "Remote: $SERVER:$REMOTE_DIR"
echo ""

# 1. Copy changed Python files
echo "Copying bot/deepseek_autoresearch_agent.py..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/bot/deepseek_autoresearch_agent.py" \
  "$SERVER:$REMOTE_DIR/bot/deepseek_autoresearch_agent.py"

echo "Copying smart_pump_reversal_bot.py..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$LOCAL_DIR/smart_pump_reversal_bot.py" \
  "$SERVER:$REMOTE_DIR/smart_pump_reversal_bot.py"

# 2. Patch .env on server to add TG_ADMIN_USER_ID
echo ""
echo "Patching .env on server..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "
  cd $REMOTE_DIR
  # Add TG_ADMIN_USER_ID if not already present
  if ! grep -q 'TG_ADMIN_USER_ID' .env; then
    echo '' >> .env
    echo '# Only accept commands from this Telegram user_id' >> .env
    echo 'TG_ADMIN_USER_ID=319077869' >> .env
    echo 'Added TG_ADMIN_USER_ID=319077869 to .env'
  else
    echo 'TG_ADMIN_USER_ID already in .env — skipping'
  fi
"

# 3. Syntax check on server
echo ""
echo "Checking syntax on server..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "
  cd $REMOTE_DIR
  python3 -m py_compile bot/deepseek_autoresearch_agent.py && echo 'deepseek_agent: OK'
  python3 -c \"import ast; ast.parse(open('smart_pump_reversal_bot.py').read()); print('bot: OK')\"
"

# 4. Restart bot service
echo ""
echo "Restarting bybot service..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "
  systemctl restart bybot
  sleep 3
  systemctl status bybot --no-pager | head -8
"

echo ""
echo "=== Deploy complete! ==="
echo "New TG commands:"
echo "  /ai_audit           — full code + config audit by DeepSeek"
echo "  /ai_code <file>     — DeepSeek reads any bot file"
echo "  /ai_code strategies/alt_sloped_channel_v1.py"
echo "  /ai_code configs/server_clean.env"
echo ""
echo "TG security: только user_id=319077869 может слать команды боту."
