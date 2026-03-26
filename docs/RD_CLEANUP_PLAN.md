# R&D Cleanup Plan (Safe, Reversible)

## Goal
- Reduce project noise for faster diagnostics.
- Preserve all rejected experiments for future revisit.

## Rules
1. Do not delete immediately.
2. First move to archive namespace with metadata.
3. Keep one source of truth: `docs/WORKLOG.md`.
4. Keep active set minimal and explicit.

## Active Crypto Set (keep in root paths)
- `inplay_breakout`
- `btc_eth_midterm_pullback`
- Live diagnostics and risk/runtime scripts used for production.

## Archive Candidate Set (move to `archive/strategies_rejected/`)
- `trend_pullback_be_trail`
- `sr_break_retest_volume_v1`
- `triple_screen_v132`
- `triple_screen_v132b`
- `structure_shift_v1`
- `structure_shift_v2`
- `trendline_break_retest*`
- `flat_bounce_v2`
- `flat_bounce_v3`
- `tv_atr_trend_v1`
- `tv_atr_trend_v2`
- `btc_eth_trend_follow`
- `btc_eth_trend_follow_v2`
- `btc_eth_trend_rsi_reentry`
- `btc_eth_vol_expansion`
- `momentum_continuation`
- `trend_regime_breakout`
- `trend_pullback`
- `range_bounce`
- `donchian_breakout`
- `adaptive_range_short`
- `smart_grid`
- `funding_hold_v1` (keep only if funding branch continues)

## Migration Steps
1. Create archive folders:
   - `archive/strategies_rejected/`
   - `archive/scripts_rejected/`
2. Move files with a machine-readable manifest:
   - `archive/rejected_manifest_YYYYMMDD.csv`
3. Update `backtest/run_portfolio.py`:
   - remove archived strategy imports
   - remove names from `allowed`
   - keep references only in `docs/WORKLOG.md`
4. Add `docs/REJECTED_STRATEGIES.md` summary with:
   - reason
   - latest base/stress metrics
   - commit/date

## Exit Criteria
- `run_portfolio.py` strategy list is concise.
- No dead scripts in `scripts/` root path.
- Rejected ideas are preserved in archive + manifest.
