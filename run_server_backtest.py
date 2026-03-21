#!/usr/bin/env python3
"""Run combined server-config backtest and print results."""
import os, sys, subprocess

os.chdir(os.path.dirname(os.path.abspath(__file__)))

env = dict(os.environ)
env.update({
    "ASC1_SYMBOL_ALLOWLIST": "ATOMUSDT,LINKUSDT",
    "ASC1_ALLOW_SHORTS": "1",
    "ASC1_ALLOW_LONGS": "0",
    "ASC1_SHORT_MIN_REJECT_DEPTH_ATR": "0.75",
    "ASC1_SHORT_MAX_NEAR_UPPER_BARS": "2",
    "ASC1_SHORT_MIN_RSI": "60",
    "ASC1_SHORT_NEAR_UPPER_ATR": "0.15",
    "ASC1_CONFIRM_5M_BARS": "6",
    "ARF1_SYMBOL_ALLOWLIST": "LINKUSDT,LTCUSDT,SUIUSDT,DOTUSDT",
    "BYBIT_DATA_POLITE_SLEEP_SEC": "0.3",
    "PYTHONUNBUFFERED": "1",
})

cmd = [
    sys.executable, "-u", "backtest/run_portfolio.py",
    "--symbols", "ATOMUSDT,LINKUSDT,LTCUSDT,SUIUSDT,DOTUSDT",
    "--strategies", "alt_sloped_channel_v1,alt_resistance_fade_v1",
    "--days", "360",
    "--tag", "server_live_config_360d",
    "--starting_equity", "100",
    "--risk_pct", "0.01",
    "--leverage", "3",
    "--fee_bps", "6",
    "--slippage_bps", "2",
]

print(f"Running: {' '.join(cmd)}", flush=True)
result = subprocess.run(cmd, env=env)
sys.exit(result.returncode)
