# Alpaca v38 Hybrid Candidate — 2026-04-28

## Current best candidate

`configs/alpaca_v38_hybrid_top4_candidate.env`

Parameters:

- `top_n=4`
- `max_hold_days=22`
- `min_mom_lookback_pct=5.0`
- `stop_atr_mult=2.0`
- `target_atr_mult=3.2`
- `be_trigger_r=0.8`
- `trail_atr_mult=1.5`
- `universe_top_k=18`

## Evidence

| Window | Return | Annualized | PF | WR | Trades | Max monthly DD | Negative months |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2024-05..2026-04 | +50.77% | ~22.79% | 6.29 | 82.9% | 35 | -2.28% | 2/24 |
| 2024-05..2025-04 | +17.84% | 17.84% | 5.28 | 80.0% | 20 | -0.05% | 1/12 |
| 2025-05..2026-04 OOS | +27.95% | 27.95% | 7.85 | 86.7% | 15 | -2.28% | 1/12 |

Run dirs:

- `backtest_runs/equities_monthly_research_20260428_081347_codex_hybrid_hybrid_top4_t32_full_20260428`
- `backtest_runs/equities_monthly_research_20260428_081349_codex_hybrid_hybrid_top4_t32_y1_20260428`
- `backtest_runs/equities_monthly_research_20260428_081350_codex_hybrid_hybrid_top4_t32_y2_oos_20260428`

## Interpretation

This is better than the current base v38 on OOS return and drawdown, but it is
not yet a 40-50% annual strategy. It is a strong conservative compounding sleeve.

Do not deploy to real money before adding broker-side Alpaca protection. Current
monthly bridge approximates the sim trailing logic with high-watermark exits, but
the protection is not yet equivalent to native broker stop/trailing order
management.

## Next Research Lane

To create an income-oriented Alpaca sleeve, monthly v38 should be treated as the
slow capital-preservation layer. The higher-frequency layer should come from
intraday/swing research, not by over-levering this monthly sleeve.
