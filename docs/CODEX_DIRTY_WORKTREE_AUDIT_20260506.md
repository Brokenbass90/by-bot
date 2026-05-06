# Dirty Worktree Audit — 2026-05-06

Purpose: stop treating the local dirty tree as mysterious junk. Nothing below
should be deleted or committed blindly.

## Commit Candidates After Validation

These look useful but need focused tests before commit/push:

- `backtest/portfolio_engine.py`
  - Adds global strategy-level SL cooldown.
  - Potentially useful for whipsaw sleeves such as breakdown/inplay.
  - Risk: changes all portfolio backtests when enabled by env.

- `strategies/alt_inplay_breakdown_v1.py`
  - Adds optional legacy wrapper mode and ER gate.
  - Potentially useful for repairing breakdown regression / bear-chop overfire.
  - Needs standalone + additivity tests before live.

- `strategies/alt_sloped_momentum_v1.py`
  - Adds Efficiency Ratio gate for chop filtering.
  - Potentially useful for sloped breakout false-signal control.
  - Needs ASM1 focused WF/annual tests.

- `strategies/alt_vwap_mean_reversion_v1.py`
  - Major VWAP repair: TP1 to VWAP, wider SL, signal cap, shorter time stop.
  - Potentially useful for quiet/chop markets.
  - Needs fresh annual and additivity before promotion.

- `configs/alpaca_paper_v36_candidate.env`
  - Adds monthly trailing/SL paper-live protection knobs.
  - Useful, but must match actual Alpaca execution code before real money.

- `scripts/run_equities_monthly_v36_refresh.sh`
  - Makes regime filters env-configurable for Alpaca monthly sweeps.
  - Useful for income-lane research.

- `scripts/claude_monthly_analyst.py`
  - Adds DeepSeek fallback client.
  - Useful for cheap AI analysis, but needs a no-key/no-network smoke on server.

## Do Not Commit As-Is

- `configs/web_config.json`
  - Contains local user auth material: hashed password and TOTP secret.
  - Keep local/server-specific. Do not push.

- `configs/intraday_config_broad_trend.json`
  - Large formatting/content diff. Needs semantic diff before any decision.

- `configs/portfolio_allocator_policy.json`
  - Pauses `range_scalp` to zero risk.
  - Might be correct, but it changes live allocation policy. Needs explicit
    approval + backtest reason before deploy.

- `configs/live_candidate_core2_breakdown_arf1_20260404.env`
  - Contains breakdown ER and ARF tuning notes.
  - This is an old candidate file; do not treat it as current live truth.

## Archive / Documentation Candidates

Many root-level files such as `CLAUDE_*`, `CODEX_TASK_*`, `CODE_REVIEW_*`,
`SECURITY_CHECKLIST_*`, `STRATEGY_*`, `PHASE_3_*`, and `AI_OVERLAY_*` are useful
handoff/task material but clutter the repo root.

Preferred cleanup:

1. Move still-relevant handoffs/tasks into `docs/archive/claude_codex_20260429_20260504/`.
2. Keep only current top-level docs in `docs/`.
3. Delete only after confirming the same information exists in `docs/JOURNAL.md`
   or `docs/ROADMAP.md`.

## Runtime / Generated Noise

- `logs/`, `reports/`, `data/`, and local `backtest_runs/` are runtime artifacts.
- They should stay out of commits unless a specific report is intentionally
  promoted into `docs/`.

## Current Recommendation

1. Keep the dirty changes for now.
2. Validate and commit one topic at a time:
   - research guard / reports — already committed.
   - BRC1 promotion lane — next.
   - breakdown/ASM1/VWAP repair patches — after focused tests.
3. Do not run broad `git add .`.
