# FX/CFD V2 preregistered research gate — 2026-07-11

- Final status: **NO_LIVE_PROMOTION**.
- Evidence class: **diagnostic** (never promotion-grade while blockers remain).
- Diagnostic data: `EURUSD,GBPJPY,GBPUSD,USDJPY`.
- Promotion-valid data: `none`.
- Data-blocked: `EURJPY,EURUSD,GBPJPY,GBPUSD,USDJPY,XAUUSD`.
- Every family is evaluated as separate long-only and short-only sleeves.
- Signals use H1 close decision time; fills are rechecked by session/news window.
- Synthetic bid/ask barriers are rerun independently under base and stress spread.
- Incomplete H1 bars are removed and every unknown market-hours gap resets warmup/positions.
- Promotion blockers: `historical_news_calendar_missing; broker_costs_uncalibrated; broker_holiday_schedule_unverified; independent_feed_parity_missing; native_bid_ask_execution_parity_missing; portfolio_mark_to_market_drawdown_missing; cross_symbol_correlation_risk_missing; strict_promotion_data_gate_failed`.

| candidate | status | stress N | stress netR | stress PF | folds+ | symbols+ | concentration |
|---|---|---:|---:|---:|---:|---:|---:|
| impulse_breakout_retest_v2:long | NO_PROMOTION | 26 | -8.606039 | 0.6089209338594957 | 2/4 | 0/3 | 1.000 |
| impulse_breakout_retest_v2:short | NO_PROMOTION | 16 | -9.056463 | 0.38220944198478535 | 1/4 | 1/3 | 1.000 |
| sweep_reclaim_bounce_v2:long | NO_PROMOTION | 101 | -18.558878 | 0.7468899161651722 | 1/4 | 1/3 | 1.000 |
| sweep_reclaim_bounce_v2:short | NO_PROMOTION | 101 | -23.55695 | 0.6898719850660083 | 0/4 | 0/3 | 1.000 |
| regime_range_reversion_v2:long | NO_PROMOTION | 28 | -16.864994 | 0.39413105519344116 | 0/4 | 1/4 | 1.000 |
| regime_range_reversion_v2:short | NO_PROMOTION | 41 | -15.17722 | 0.5868486440845081 | 1/4 | 0/3 | 1.000 |

Closed-trade drawdown is diagnostic only; portfolio mark-to-market/correlation risk is a blocker.
A quantitative PASS would still be shadow-blocked until historical news, broker costs, DST/holiday contract, native bid/ask parity and independent-feed parity are complete.
No result in this report authorizes demo orders or live capital.
