# Open Tasks (Single Source of Truth)

Last update: 2026-03-04

## Done Recently
- [x] Added isolated Forex pilot module (`forex/`) with separate engine and strategy.
- [x] Added Forex CLI runner: `scripts/run_forex_backtest.py`.
- [x] Added Forex batch runner: `scripts/run_forex_pilot_batch.sh`.
- [x] Fixed Forex batch runner for macOS Bash 3.2 (no associative arrays).
- [x] Added R&D focus policy: `docs/RD_FOCUS_RULES.md`.
- [x] Added cleanup plan: `docs/RD_CLEANUP_PLAN.md`.
- [x] Added rejected candidates inventory: `docs/rd_cleanup_candidates.csv`.
- [x] Added old runs catalog: `docs/backtest_runs_catalog.csv`.

## In Progress
- [ ] Live diagnostics-driven tuning for breakout+midterm (production stack).
  - Current blocker (2026-03-04 overnight): zero entries (`breakout_try=16097`, `entry=0`; `midterm_try=682`, `entry=0`).
  - Measured reason mix: no-signal mostly `impulse` (`13230 / 16049 = 82.44%`), then `symbol` (`1938 / 16049 = 12.08%`), then `no_break` (`4.65%`).
  - Impulse-only sweep checkpoint (180d):
    - `0.80`: base `+18.88`, stress `+3.60`, trades `213` (stress)
    - `0.75`: base `+19.09`, stress `+3.96`, trades `213` (stress)
    - `0.70`: base `+19.09`, stress `+3.96`, trades `213` (stress)
  - Canary result in live (2026-03-03 17:59 UTC deploy): `BREAKOUT_IMPULSE_ATR_MULT=0.75` did not unlock entries overnight.
  - Guardrail checks:
    - `BREAKOUT_IMPULSE_BODY_MIN_FRAC=0.20` degrades stress (180d: `96.84`, `-3.16`, `DD 7.18`) -> reject.
    - `BREAKOUT_IMPULSE_BODY_MIN_FRAC=0.30` near flat but still worse than baseline (180d stress: `99.86`, `-0.14`, `DD 6.07`) -> reject.
  - Next canary: keep body filter intact, investigate `symbol` blockers and split impulse diagnostics into sub-reasons (`weak/body/vol`).
- [ ] Cleanup phase 1: archive-first strategy/scripts restructuring (no destructive deletes).
  - Technical prerequisite: `backtest/run_portfolio.py` still has static imports for many rejected strategies, so physical file move must happen together with import/allowed-list pruning in one change-set.
  - Gap report generated: `docs/cleanup_gap_report.csv`
    - `prune_import_before_archive=33`
    - `archive_ready=1` (`funding_hold_v1.py`)
- [ ] Forex data pipeline: load M5 CSV for EURUSD/GBPUSD/USDJPY into `data_cache/forex/`.
  - Data readiness report generated: `docs/forex_data_status.csv` (`ready=0/3`, all three CSV files missing).

## Next Actions (Priority Order)
1. Capture next live diagnostics window and decide one minimal canary change in breakout thresholds.
2. Commit cleanup metadata and move rejected strategies to archive namespace with manifest.
3. Run first Forex batch once CSV files exist and store summary in `backtest_runs/`.
4. Build simple pass/fail gate report for crypto candidates (base+stress).

## Blocked / Waiting
- Forex pilot backtest is blocked by missing local CSV files:
  - `data_cache/forex/EURUSD_M5.csv`
  - `data_cache/forex/GBPUSD_M5.csv`
  - `data_cache/forex/USDJPY_M5.csv`

## Rule Reminder
- If no crypto candidate passes both base+stress for 10-14 days, shift 50% R&D to Forex.
