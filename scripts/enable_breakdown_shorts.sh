#!/bin/bash
# Enable breakdown shorts strategy on server (alt_inplay_breakdown_v1)
# Params confirmed by autoresearch: r003 PF=2.085 WR=54.3% 127 trades DD=2.41%
# Run from your local terminal: bash scripts/enable_breakdown_shorts.sh

SSH_KEY="${SSH_KEY:-~/.ssh/by-bot}"
SERVER="root@64.226.73.119"

echo "=== Enabling Breakdown Shorts on Server ==="
echo "Backtest result: PF=2.085 WR=54.3% 127trades/year DD=2.41% 1 red month"
echo ""
echo "Params: REGIME_MODE=off LOOKBACK_H=48 RR=2.0 SL_ATR=1.8 MAX_DIST=2.0"
echo "Coins: BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ATOMUSDT"
echo ""

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" "
  cd /root/by-bot

  # Backup current .env
  cp .env .env.bak_breakdown_\$(date +%Y%m%d_%H%M%S)
  echo 'Backup created.'

  # Patch BREAKDOWN params to confirmed best
  sed -i 's/^ENABLE_BREAKDOWN_TRADING=.*/ENABLE_BREAKDOWN_TRADING=1/' .env
  sed -i 's/^BREAKDOWN_REGIME_MODE=.*/BREAKDOWN_REGIME_MODE=off/' .env
  sed -i 's/^BREAKDOWN_LOOKBACK_H=.*/BREAKDOWN_LOOKBACK_H=48/' .env
  sed -i 's/^BREAKDOWN_RR=.*/BREAKDOWN_RR=2.0/' .env
  sed -i 's/^BREAKDOWN_SL_ATR=.*/BREAKDOWN_SL_ATR=1.8/' .env
  sed -i 's/^BREAKDOWN_MAX_DIST_ATR=.*/BREAKDOWN_MAX_DIST_ATR=2.0/' .env

  # Remove old EMA regime params (not needed with REGIME_MODE=off)
  sed -i '/^BREAKDOWN_REGIME_TF=/d' .env
  sed -i '/^BREAKDOWN_REGIME_EMA_FAST=/d' .env
  sed -i '/^BREAKDOWN_REGIME_EMA_SLOW=/d' .env

  echo 'Breakdown params applied.'
  echo ''
  echo 'Current BREAKDOWN settings:'
  grep 'BREAKDOWN_\|ENABLE_BREAKDOWN' .env

  echo ''
  echo 'Restarting bot...'
  systemctl restart bybot
  sleep 3
  systemctl status bybot --no-pager | head -6
"

echo ""
echo "=== Done ==="
echo "Watch for breakdown trades in Telegram."
echo "To disable: ssh root@64.226.73.119 \"sed -i 's/ENABLE_BREAKDOWN_TRADING=1/ENABLE_BREAKDOWN_TRADING=0/' /root/by-bot/.env && systemctl restart bybot\""
