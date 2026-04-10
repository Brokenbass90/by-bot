# Equity Curve Autopilot Report
**Date:** 2026-04-03 13:19 UTC
**Run:** `portfolio_20260403_150051_validated_baseline_regression_20260403_120047`
**Overall Health:** WATCH

## Per-Strategy Health

| Strategy | Status | Total PnL | 30d PnL | 60d PnL | Trades | WR 30d | PF 30d | Curve vs MA |
|---|---|---|---|---|---|---|---|---|
| alt_inplay_breakdown_v1 | WATCH | -12.441 | +1.081 | -1.549 | 67 (3/30d) | 0% | 0.00 | -2.340 |
| alt_resistance_fade_v1 | OK | 13.493 | +2.280 | +5.805 | 63 (3/30d) | 0% | 0.00 | +4.743 |
| alt_sloped_channel_v1 | OK | 4.899 | -2.279 | -2.260 | 28 (4/30d) | 0% | 0.00 | +1.098 |
| btc_eth_midterm_pullback | OK | 6.353 | -0.528 | +1.408 | 34 (1/30d) | 0% | 0.00 | +1.444 |
| inplay_breakout | OK | -1.062 | +0.000 | -0.527 | 19 (0/30d) | 0% | 0.00 | +0.000 |

## Status Legend
- **OK** — Equity curve above MA, recent P&L positive. Normal operation.
- **WATCH** — Curve below MA20. Monitor closely, no action yet.
- **PAUSE** — 30d rolling P&L negative. Stop new entries, run autoresearch.
- **KILL** — 60d rolling P&L strongly negative. Disable strategy, investigate.

## Paused/Kill Strategies
None — all strategies within acceptable ranges.