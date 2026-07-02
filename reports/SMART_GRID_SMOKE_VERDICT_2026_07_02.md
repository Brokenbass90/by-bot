# Smart grid smoke verdict — 2026-07-02

Purpose: verify that the new `bot.smart_grid` mechanics can be run through
`backtest/run_portfolio.py` before spending time on a full OOS gate.

## What changed

Added `strategies/smart_grid.py`, a research-only adapter around
`bot.smart_grid.grid_plan`.

It replaces the retired archive import path for `--strategies smart_grid` and
models a one-order grid proxy:

- range-only planner from `bot.smart_grid`;
- limit order at nearest grid level;
- stop beyond channel boundary;
- target at channel midpoint;
- portfolio engine handles limit fill/expiry.

This is not a live multi-order grid executor.

## Smoke command

```bash
BACKTEST_CACHE_ONLY=1 \
SG_REQUIRE_FLAT_REGIME=0 \
SG_MIN_WIDTH_ATR=1.0 \
SG_MIN_RR=0.1 \
SG_MAX_STOP_PCT=0.20 \
.venv/bin/python backtest/run_portfolio.py \
  --symbols ADAUSDT,DOGEUSDT,SUIUSDT,DOTUSDT,LTCUSDT,LINKUSDT,SOLUSDT \
  --strategies smart_grid \
  --days 120 --end 2026-06-30 \
  --starting_equity 100 --risk_pct 0.005 --leverage 1 --max_positions 3 \
  --fee_bps 6 --slippage_bps 2 --entry-on-next-open \
  --tag smart_grid_smoke_20260702
```

Output:

- `backtest_runs/portfolio_20260702_100219_smart_grid_smoke_20260702/summary.csv`
- `backtest_runs/portfolio_20260702_100219_smart_grid_smoke_20260702/trades.csv`

## Result

| metric | value |
|---|---:|
| trades | 1908 |
| net | -86.72 |
| PF | 0.343 |
| WR | 42.3% |
| max DD | 86.73 |

By symbol:

| symbol | trades | net |
|---|---:|---:|
| LTCUSDT | 135 | -4.92 |
| ADAUSDT | 266 | -6.80 |
| SOLUSDT | 207 | -10.26 |
| LINKUSDT | 234 | -10.91 |
| DOGEUSDT | 258 | -15.15 |
| DOTUSDT | 370 | -16.51 |
| SUIUSDT | 438 | -22.17 |

By side:

| side | trades | net |
|---|---:|---:|
| long | 963 | -48.12 |
| short | 945 | -38.60 |

## Read

The current one-order grid proxy is **not an edge**. It is too high frequency
and the average target is too small relative to fees/slippage. Some trades show
`outcome=tp` with negative net PnL after costs, which is a direct sign that the
grid step / reward geometry is below cost floor.

## Decision

- Do not run full OOS gate on this version.
- Do not put smart_grid into live/shadow as currently configured.
- Next useful grid work, if any:
  1. enforce minimum gross target after fees;
  2. require wider channel/step;
  3. reduce frequency aggressively;
  4. retest only after a cheap smoke turns PF > 1 and DD is bounded.

