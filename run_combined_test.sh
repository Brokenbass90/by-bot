#!/bin/bash
export ARF1_SYMBOL_ALLOWLIST=LINKUSDT,LTCUSDT,SUIUSDT
export ASC1_SYMBOL_ALLOWLIST=LINKUSDT,ATOMUSDT,SOLUSDT
export ASC1_CONFIRM_5M_BARS=6
export ASC1_SHORT_MIN_REJECT_VOL_MULT=0.0

python3 backtest/run_portfolio.py \
  --symbols LINKUSDT,ATOMUSDT,SOLUSDT,LTCUSDT,SUIUSDT \
  --strategies alt_sloped_channel_v1,alt_resistance_fade_v1 \
  --days 365 \
  --tag combined_v2_365d \
  > /tmp/combined_v2.log 2>&1

echo "EXIT: $?" >> /tmp/combined_v2.log
