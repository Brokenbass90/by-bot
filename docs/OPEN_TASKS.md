# Open Tasks (Single Source of Truth)

Last update: 2026-03-03

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
  - Current blocker (2026-03-03, 2h): zero entries (`breakout_try=1601`, `entry=0`; `midterm_try=78`, `entry=0`).
  - Measured reason mix: no-signal mostly `impulse` (`1289 / 1595 = 80.82%`), then `other` (`200 / 1595 = 12.54%`), then `no_break` (`6.39%`).
  - Impulse-only sweep checkpoint (180d):
    - `0.80`: base `+18.88`, stress `+3.60`, trades `213` (stress)
    - `0.75`: base `+19.09`, stress `+3.96`, trades `213` (stress)
    - `0.70`: base `+19.09`, stress `+3.96`, trades `213` (stress)
  - Candidate canary: `BREAKOUT_IMPULSE_ATR_MULT=0.75` (minimal loosening with slight stress improvement in backtest).
- [ ] Cleanup phase 1: archive-first strategy/scripts restructuring (no destructive deletes).
  - Technical prerequisite: `backtest/run_portfolio.py` still has static imports for many rejected strategies, so physical file move must happen together with import/allowed-list pruning in one change-set.
- [ ] Forex data pipeline: load M5 CSV for EURUSD/GBPUSD/USDJPY into `data_cache/forex/`.

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
