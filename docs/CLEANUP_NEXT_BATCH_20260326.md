# Cleanup Next Batch 2026-03-26

This file defines the next safe cleanup batches. No batch below should be executed blindly.

## Batch A — Deploy Surface Cleanup

Goal: reduce operator confusion without touching strategy logic.

### Already done
- Canonical local env moved to `.env`
- Canonical server env confirmed as `/root/by-bot/.env`
- Redacted reference added: `configs/server.env.example`
- Deploy surface inventory added: `docs/DEPLOY_SURFACE_INVENTORY_20260326.md`

### Next actions
1. Keep documenting `scripts/deploy_session10.sh` as the default local deploy path.
2. Keep `scripts/deploy_all_latest.sh` only as a broad manual sync helper.
3. Mark dated deploy scripts as historical in docs before any deletion:
   - `scripts/deploy_session9.sh`
   - `scripts/deploy_full_20260318.sh`
   - `scripts/deploy_live_evening_20260319.sh`
   - `scripts/deploy_sloped_atom_canary_20260318.sh`
   - `scripts/deploy_to_server.sh`

### Why this batch is safe
- documentation and classification only
- no live strategy behavior changes
- no secret rotation required

## Batch B — Strategy Archive Preparation

Goal: prepare the repo for archive-first cleanup without breaking `run_portfolio.py`.

### Current blocker
- `docs/cleanup_gap_report.csv` still shows `33` archive candidates that remain statically imported in `backtest/run_portfolio.py`

### Next actions
1. Prune imports/allowed-list for archive candidates in one controlled change-set.
2. Only after that, move rejected strategies into archive namespace with manifest.

### Already identified archive candidates
- `trend_pullback*`
- `trendline_break_retest*`
- `triple_screen_v132*`
- `flat_bounce_v2/v3`
- `tv_atr_trend_v1/v2`
- `btc_eth_trend_follow*`
- `range_bounce`
- `donchian_breakout`
- `smart_grid`

## Batch C — Runtime / Artifact Cleanup

Goal: reduce workspace noise after logic cleanup is stable.

### Candidates
- stale `backtest_runs/` leftovers already summarized elsewhere
- legacy handoff docs superseded by `WORKLOG.md`
- runtime scratch data that is safe to regenerate

### Rule
- archive or index first
- delete later in small reversible batches

## Not In Scope Yet
- secret rotation
- Alpaca live rollout
- TS132 live rollout
- scalper live rollout
- forex/CFD expansion

These come after current crypto stack cleanup and observability stabilization.
