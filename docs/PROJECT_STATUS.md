# Project Status (Short)

## Goal
Build a multi-strategy crypto trading system with controlled drawdown and stable monthly returns via regime diversification.

## Current baseline
- Strategy: `inplay_breakout`
- Baseline run: `baselines/inplay_v10_combo_deny_360d`
- 360d headline: `ending_equity=126.79`, `net=+26.79`, `PF=20.37`, `max_drawdown=0.52%`
- Robust windows (`120/180/240/300d`): all net-positive, but some negative months remain.

## What is done
- Dynamic per-strategy symbol filters (`build_symbol_filters.py` + trade-driven deny updates).
- Inplay hardening: anti-late/anti-fomo guards, runner exits, cooldown logic.
- Trade visual diagnostics in bot (`/plotlast`, `/plotts`) with entry/exit/TP/SL overlays.
- Reporting via Telegram (`/stats` + CSV/PNG).

## Current risks
- Inplay alone does not guarantee every month positive.
- PnL concentration in a few strong trend months/symbols.
- Need orthogonal strategy for range/depressive regimes.

## Active next block
- New strategy in progress: `adaptive_range_short`
- Intent: range-mode mean-reversion with trend gate and kill-switch.
- Safety constraints: kill-cooldown, per-day signal cap, cooldown bars, RR floor.

## Next milestones
1. Backtest `adaptive_range_short` on same filtered universe.
2. Build portfolio combo: `inplay_breakout + adaptive_range_short`.
3. Compare monthly stability and drawdown versus inplay-only baseline.
4. Decide live rollout parameters.
