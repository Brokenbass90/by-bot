# BRC1 sanity verdict — 2026-07-02

Server autoresearch showed attractive 90d rows for
`alt_bear_regime_continuation_v1` (`BRC1`), e.g. r005:

- 31 trades
- net +6.15
- PF 4.80
- DD 0.40

That looked like a possible second crypto sleeve after ATT1, so it was checked
on a longer local cache-only 360d window before spending time on a full OOS gate.

## Sanity command

```bash
BACKTEST_CACHE_ONLY=1 \
BRC1_MIN_REJECT_WICK_RATIO=0.8 \
BRC1_PULLBACK_BARS=3 \
BRC1_PULLBACK_MIN_PCT=0.25 \
BRC1_RR=1.3 \
BRC1_RSI_MAX=68 \
BRC1_RSI_MIN=45 \
.venv/bin/python backtest/run_portfolio.py \
  --symbols SOLUSDT,ADAUSDT,DOTUSDT,LINKUSDT,SUIUSDT,LTCUSDT \
  --strategies alt_bear_regime_continuation_v1 \
  --days 360 --end 2026-06-30 \
  --starting_equity 100 --risk_pct 0.0075 --leverage 1 --max_positions 3 \
  --fee_bps 6 --slippage_bps 2 --entry-on-next-open \
  --tag brc1_r005_360d_sanity_20260702
```

Output:

- `backtest_runs/portfolio_20260702_100523_brc1_r005_360d_sanity_20260702/summary.csv`
- `backtest_runs/portfolio_20260702_100523_brc1_r005_360d_sanity_20260702/trades.csv`

## Result

| metric | value |
|---|---:|
| trades | 93 |
| net | +1.26 |
| PF | 1.080 |
| WR | 51.6% |
| DD | 3.1267 |

By symbol:

| symbol | trades | net |
|---|---:|---:|
| SUIUSDT | 18 | +1.20 |
| DOTUSDT | 22 | +0.78 |
| SOLUSDT | 13 | +0.31 |
| ADAUSDT | 23 | -0.48 |
| LINKUSDT | 17 | -0.55 |

By month:

| month | trades | net |
|---|---:|---:|
| 2025-07 | 4 | +0.11 |
| 2025-08 | 3 | -0.46 |
| 2025-10 | 19 | +0.01 |
| 2025-11 | 16 | +2.06 |
| 2025-12 | 8 | -0.59 |
| 2026-01 | 6 | +1.23 |
| 2026-02 | 25 | -0.09 |
| 2026-05 | 1 | -0.10 |
| 2026-06 | 11 | -0.93 |

## Decision

- Do not add BRC1 to live/canary from the 90d pocket.
- The 90d server pass was regime-local; the longer 360d sanity is only barely positive.
- If BRC1 remains interesting, next step is side/symbol/month filtering and strict
  rolling OOS, not direct promotion.

