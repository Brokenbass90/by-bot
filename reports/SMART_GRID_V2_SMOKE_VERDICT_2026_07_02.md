# SmartGrid v2 smoke verdict — 2026-07-02

Scope: cache-only 120d portfolio smoke on `ADAUSDT,DOGEUSDT,SUIUSDT,DOTUSDT,LTCUSDT,LINKUSDT,SOLUSDT`.

Command:

```bash
BACKTEST_CACHE_ONLY=1 SG_REQUIRE_STRONG_FLAT=1 SG_MIN_WIDTH_ATR=1.0 SG_MIN_RR=0.1 SG_MAX_STOP_PCT=0.20 SG_FEE_BPS=6 SG_FEE_SURVIVAL_MULT=3 \
  .venv/bin/python backtest/run_portfolio.py \
  --symbols ADAUSDT,DOGEUSDT,SUIUSDT,DOTUSDT,LTCUSDT,LINKUSDT,SOLUSDT \
  --strategies smart_grid \
  --days 120 --end 2026-06-30 \
  --starting_equity 100 --risk_pct 0.005 --leverage 1 --max_positions 3 \
  --fee_bps 6 --slippage_bps 2 --entry-on-next-open \
  --tag smart_grid_v2_smoke_20260702
```

Run:

- `backtest_runs/portfolio_20260702_104511_smart_grid_v2_smoke_20260702`

Summary:

| version | trades | net | PF | WR | max DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| v1 smoke | 1908 | -86.72 | 0.343 | 42.3% | 86.73 |
| v2 smoke | 249 | -12.62 | 0.436 | 69.1% | 12.77 |

Diagnostics:

| slice | trades | net | PF | WR |
| --- | ---: | ---: | ---: | ---: |
| flat | 81 | -3.03 | 0.533 | 71.6% |
| ascending | 76 | -5.15 | 0.340 | 64.5% |
| descending | 92 | -4.44 | 0.451 | 70.7% |
| long | 115 | -7.35 | 0.379 | 65.2% |
| short | 134 | -5.27 | 0.500 | 72.4% |

Verdict:

- v2 materially reduces damage versus v1, so the fee-aware/strong-flat fixes are directionally correct.
- It is still not a canary candidate: every main slice remains negative after fees/slippage.
- The current `strategies/smart_grid.py` is a one-order research proxy, not a production multi-order grid executor.
- Keep SmartGrid research-only. Do not deploy live until a side-specific OOS gate passes and a real multi-order executor supports order placement/cancel/kill-flatten.

Next:

1. If continuing grid research, test side-specific `SG_SIDE=long|short` and require OOS plateau, not a single-symbol pocket.
2. Higher priority remains ARF2 exhaustion/failed-breakout rewrite and FX/H4 real-data research.
