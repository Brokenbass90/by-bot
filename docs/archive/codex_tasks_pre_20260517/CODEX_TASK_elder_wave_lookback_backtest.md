# Codex Task: Elder Wave Lookback Backtest

## Summary of Fix Applied

`strategies/elder_triple_screen_v2.py` was updated with a critical Screen 2 fix.
**The fix is already in the code — do NOT revert it.**

### Root Cause (diagnosed)
Screen 2 checked RSI only at the CURRENT 1H bar. But Screen 3 fires on the RECLAIM 15m candle
(i.e., after price has already bounced off support). By that time RSI has already recovered above 42.
Result: Screen 2 blocked every valid Elder entry. 0 trades across 800+ backtest runs.

### Fix Applied
Screen 2 now checks if RSI was in the pullback zone within the last `wave_lookback` 1H bars (default=3).
New env var: `ETS2_WAVE_LOOKBACK` (default 3). Controls how many recent bars to scan.

---

## Your Task: Run the Backtest

Create and run an autoresearch spec: `configs/autoresearch/elder_wave_lookback_v1.json`

### Spec Requirements

```json
{
    "name": "elder_wave_lookback_v1",
    "cache_only": true,
    "command": [
        "{python}", "backtest/run_portfolio.py",
        "--symbols", "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT",
        "--strategies", "elder_triple_screen_v2",
        "--days", "360",
        "--end", "2026-04-01",
        "--tag", "{tag}",
        "--starting_equity", "100",
        "--risk_pct", "0.005",
        "--leverage", "1",
        "--max_positions", "3",
        "--fee_bps", "6",
        "--slippage_bps", "2"
    ],
    "base_env": {
        "ETS2_ALLOW_LONGS": "1",
        "ETS2_ALLOW_SHORTS": "1",
        "ETS2_TREND_TF": "240",
        "ETS2_TREND_EMA": "13",
        "ETS2_WAVE_TF": "60",
        "ETS2_OSC_TYPE": "rsi",
        "ETS2_OSC_PERIOD": "8",
        "ETS2_ENTRY_TF": "15",
        "ETS2_ENTRY_LOOKBACK": "5",
        "ETS2_RISK_TF": "60",
        "ETS2_SL_ATR_MULT": "2.0",
        "ETS2_TRAIL_ATR_MULT": "1.0",
        "ETS2_TIME_STOP_BARS_5M": "576",
        "ETS2_SYMBOL_ALLOWLIST": "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT"
    },
    "grid": {
        "ETS2_WAVE_LOOKBACK": [2, 3, 5],
        "ETS2_OSC_OB": [55, 58, 62],
        "ETS2_OSC_OS": [38, 42, 46],
        "ETS2_ENTRY_RETEST_BARS": [4, 5, 7],
        "ETS2_ENTRY_TOUCH_ATR_MULT": [0.25, 0.50],
        "ETS2_TP_ATR_MULT": [2.0, 2.5, 3.0],
        "ETS2_TREND_SLOPE_BARS": [1, 2, 3],
        "ETS2_COOLDOWN_BARS_5M": [6, 12]
    },
    "constraints": {
        "min_trades": 6,
        "min_profit_factor": 1.03,
        "min_net_pnl": 1.0,
        "max_neg_months": 5,
        "max_neg_streak": 3
    }
}
```

### After Running

1. Read `ranked_results.csv` — find best runs with trades > 20, PF > 1.1
2. If best PF > 1.2 and trades > 30:
   - Update defaults in `ElderTripleScreenV2Config` with winning parameters
   - Add `ETS2_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT` to `configs/core3_live_canary_20260410.env`
   - Report: "Elder is live — best params: WAVE_LOOKBACK=X, OSC_OS=Y, PF=Z, trades=N"
3. If no runs pass with PF > 1.1:
   - Try wider `ETS2_WAVE_LOOKBACK` values up to 6
   - Report failure with top-3 results and their no-signal reasons

### Definition of Done
- Backtest run completes (all grid combinations)
- Winner params applied to live config (if passing)
- Summary reported: trades/PF/WR/DD for best config
