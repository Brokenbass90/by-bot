# Equity Curve Autopilot Report
**Date:** 2026-03-29 06:56 UTC
**Run:** `portfolio_20260325_172613_new_5strat_final`
**Overall Health:** WATCH

## Per-Strategy Health

| Strategy | Status | Total PnL | 30d PnL | 60d PnL | Trades | WR 30d | PF 30d | Curve vs MA |
|---|---|---|---|---|---|---|---|---|
| alt_inplay_breakdown_v1 | WATCH | 34.852 | +0.000 | +1.445 | 157 (0/30d) | 0% | 0.00 | -0.968 |
| alt_resistance_fade_v1 | OK | 29.788 | +0.000 | +4.218 | 55 (0/30d) | 0% | 0.00 | +6.095 |
| alt_sloped_channel_v1 | OK | 16.181 | +0.000 | -1.177 | 77 (0/30d) | 0% | 0.00 | +2.179 |
| btc_eth_midterm_pullback | OK | 3.578 | +0.000 | +1.937 | 46 (0/30d) | 0% | 0.00 | +1.026 |
| inplay_breakout | OK | 16.533 | +0.000 | +0.947 | 111 (0/30d) | 0% | 0.00 | +4.015 |

## Status Legend
- **OK** — Equity curve above MA, recent P&L positive. Normal operation.
- **WATCH** — Curve below MA20. Monitor closely, no action yet.
- **PAUSE** — 30d rolling P&L negative. Stop new entries, run autoresearch.
- **KILL** — 60d rolling P&L strongly negative. Disable strategy, investigate.

## Paused/Kill Strategies
None — all strategies within acceptable ranges.