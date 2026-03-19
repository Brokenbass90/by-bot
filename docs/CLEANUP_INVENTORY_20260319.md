# Cleanup Inventory 2026-03-19

This is an inventory, not a deletion plan. The repo is dirty and active, so nothing below should be removed blindly.

## Counts
- Active strategy directory: `strategies/` -> `20` Python files
- Retired/archive strategy directory: `archive/strategies_retired/` -> `38` Python files

## Keep As Active Core
- `strategies/alt_sloped_channel_v1.py`
- `strategies/sloped_channel_live.py`
- `strategies/btc_cycle_pullback_v1.py`
- `strategies/btc_regime_retest_v1.py`
- `strategies/btc_regime_flip_continuation_v1.py`
- `strategies/btc_sloped_reclaim_v1.py`
- `strategies/inplay_breakout.py`
- `strategies/signals.py`

## Keep As Research Branches
- `strategies/alt_range_reclaim_v1.py`
- `strategies/alt_resistance_fade_v1.py`
- `strategies/btc_cycle_continuation_v1.py`
- `strategies/btc_cycle_level_target_v2.py`
- `strategies/btc_daily_level_reclaim_v1.py`
- `strategies/btc_swing_zone_reclaim_v1.py`
- `strategies/btc_weekly_zone_reclaim_v2.py`
- `archive/strategies_retired/triple_screen_v132.py`
- `archive/strategies_retired/trendline_break_retest_v4.py`

## Archive Review Candidates
- `archive/strategies_retired/flat_bounce_v2.py`
- `archive/strategies_retired/flat_bounce_v3.py`
- `archive/strategies_retired/smart_grid.py`
- `archive/strategies_retired/smart_grid_v2.py`
- `archive/strategies_retired/smart_grid_v3.py`
- `archive/strategies_retired/trendline_break_retest.py`
- `archive/strategies_retired/trendline_break_retest_v2.py`
- `archive/strategies_retired/trendline_break_retest_v3.py`
- `archive/strategies_retired/tv_atr_trend_v1.py`
- `archive/strategies_retired/tv_atr_trend_v2.py`
- `archive/strategies_retired/btc_eth_trend_follow.py`
- `archive/strategies_retired/btc_eth_trend_follow_v2.py`

Reason: these are not necessarily bad, but they overlap with newer branches and should be classified as `reference only`, `retest later`, or `safe to remove`.

## Documentation Drift To Fix
- `docs/AUDIT_20260318.md` is outdated on live wiring. It still implies `sloped` and `TS132` are not wired, while current code already contains the hooks.
- `docs/SESSION_CACHE.md` and `docs/WORKLOG.md` have fresher truth than the audit doc right now.

## Runtime / Backtest Cleanup Candidates
- old `backtest_runs/autoresearch_*` directories from failed or partial runs
- stale live diagnostic outputs after they are summarized into docs
- obsolete config variants once a newer spec fully replaces them

## Safe Cleanup Process
1. Classify every candidate as `active`, `research`, `reference`, or `delete-later`.
2. Update docs so the classification is explicit.
3. Only after that, archive or delete low-value files in small batches.
4. Never clean while a long run depends on the file set being touched.

## Near-Term Focus
- do not remove anything yet
- first finish classification around flat families, TS132, and Alpaca configs
- then clean archive overlap and outdated docs
