# CODEX TASK: Backtest two new sloped strategies (ATT1 + ASM1)

## Context
Two new strategies have been written and wired into run_portfolio.py:
1. `alt_trendline_touch_v1` (ATT1) — swing-pivot trendline bounce (long + short)
2. `alt_sloped_momentum_v1` (ASM1) — sloped channel breakout momentum (long + short)

These are the PRIMARY new strategies for sloped-level trading. They complement
the existing flat-level strategies (ARF1 = horizontal resistance fade).

Also test the existing sloped strategies that have never been honestly backtested:
3. `alt_sloped_channel_v1` (ASC1) — existing mean-reversion inside sloped channel
4. `sloped_break_retest_v1` (SBR1) — existing breakout + retest

## Goals
For each strategy:
1. Does it produce any trades? (minimum 15/year to be worth deploying)
2. Is PF > 1.15 (out-of-sample threshold for consideration)?
3. Are the trades distributed across time (not clustered in one period)?
4. What are the best parameter configurations?

## Run A — ATT1 initial probe (90-day recent window)

```bash
$PYTHON backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT \
  --strategies alt_trendline_touch_v1 \
  --days 360 --end 2026-04-01 \
  --tag att1_initial_probe_v1 \
  --risk_pct 0.01 --leverage 1 --fee_bps 6 --slippage_bps 2
```

If trades > 0, run an autoresearch sweep over:
```json
{
  "ATT1_PIVOT_LEFT": [2, 3, 4],
  "ATT1_PIVOT_RIGHT": [2, 3],
  "ATT1_MIN_PIVOTS": [2, 3],
  "ATT1_MAX_PIVOT_AGE": [12, 20],
  "ATT1_MIN_R2": [0.70, 0.80, 0.90],
  "ATT1_TOUCH_ATR": [0.25, 0.35, 0.50],
  "ATT1_RSI_LONG_MAX": [52, 55, 60],
  "ATT1_RSI_SHORT_MIN": [40, 45, 48]
}
```

## Run B — ASM1 initial probe

```bash
$PYTHON backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT,XRPUSDT \
  --strategies alt_sloped_momentum_v1 \
  --days 360 --end 2026-04-01 \
  --tag asm1_initial_probe_v1 \
  --risk_pct 0.01 --leverage 1 --fee_bps 6 --slippage_bps 2
```

If trades > 0, run a sweep over:
```json
{
  "ASM1_MIN_R2": [0.25, 0.35, 0.45],
  "ASM1_BREAKOUT_EXT_ATR": [0.10, 0.15, 0.25],
  "ASM1_MIN_BODY_FRAC": [0.25, 0.35, 0.45],
  "ASM1_VOL_MULT": [1.20, 1.50, 2.00],
  "ASM1_MIN_SLOPE_PCT": [0.05, 0.10, 0.20],
  "ASM1_USE_TREND_FILTER": ["0", "1"]
}
```

## Run C — Combined portfolio (ATT1 + ASM1 + ARF1 + Breakdown)

Once both strategies have passing configs, test the full portfolio:

```bash
$PYTHON backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT \
  --strategies alt_trendline_touch_v1,alt_sloped_momentum_v1,alt_resistance_fade_v1,alt_inplay_breakdown_v1 \
  --days 360 --end 2026-04-01 \
  --tag sloped_full_portfolio_probe_v1 \
  --risk_pct 0.01 --leverage 1 --fee_bps 6 --slippage_bps 2
```

## Run D — Audit existing sloped strategies (ASC1 + SBR1)

```bash
$PYTHON backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT \
  --strategies alt_sloped_channel_v1,sloped_break_retest_v1 \
  --days 360 --end 2026-04-01 \
  --tag sloped_existing_audit_v1 \
  --risk_pct 0.01 --leverage 1 --fee_bps 6 --slippage_bps 2
```

## Decision criteria

| Condition | Action |
|---|---|
| trades < 10/year | 🔴 Not viable — skip or redesign |
| trades 10-30/year, PF > 1.15 | 🟡 Low frequency — add to portfolio at 0.5× risk |
| trades > 30/year, PF > 1.15 | 🟢 Add to live config at full risk |
| trades > 30/year, PF > 1.30 | 🟢🟢 Priority — run full autoresearch sweep |
| PF < 1.0 across all params | 🔴 Strategy logic likely flawed — report to human |

## Output

For each strategy that passes, write the best params to:
`configs/autoresearch/sloped_strategies_best_v1.json`

Format:
```json
{
  "ATT1": {
    "status": "pass",
    "pf": 1.XX,
    "trades": XX,
    "params": {"ATT1_PIVOT_LEFT": "3", ...}
  },
  "ASM1": { ... },
  "ASC1_audit": { ... },
  "SBR1_audit": { ... }
}
```

## Important notes

- ATT1 uses swing pivot detection. If trades = 0, check:
  1. Are pivot_left/pivot_right too large (filtering all swings)?
  2. Is max_pivot_age too small (no recent valid pivots)?
  3. Is min_r2 too strict for 2-point trendlines?
  For 2-point trendlines, R² is always 1.0 — min_r2 only matters for 3+ pivots.

- ASM1 won't fire unless slope_pct is meaningful. On sideways coins (ER < 0.3),
  the regression will have low slope → filtered out. This is CORRECT behavior.
  For horizontal breakouts use alt_inplay_breakdown_v1.

- Both strategies have trailing stops — backtest engine must support
  `trailing_atr_mult` and `trail_activate_rr` fields on TradeSignal.
  Verify via: grep "trail_activate_rr" backtest/engine.py
