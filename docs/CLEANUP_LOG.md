# Cleanup Log (Archive-First)

Purpose: track every cleanup action, reason, and effect.

## Fields
- date_utc
- scope
- action
- reason
- expected_effect
- observed_effect
- reversible

## Entries
| date_utc | scope | action | reason | expected_effect | observed_effect | reversible |
|---|---|---|---|---|---|---|
| 2026-03-03 | `backtest_runs/*` | moved historical runs to `backtest_runs/old` | reduce noise in active run folder | faster navigation, less accidental reuse | active `backtest_runs` now compact | yes |
| 2026-03-03 | `backtest_runs/old` | indexed into `docs/backtest_runs_catalog.csv` (489 rows) | keep experiment memory before deletion/archive | prevent duplicate reruns of old ideas | catalog file generated and usable | yes |
| 2026-03-03 | `docs/rd_cleanup_candidates.csv` | generated keep/archive candidate map | explicit active-vs-rejected split | cleaner future imports and scans | keep_active=4, archive_candidate=34 | yes |
| 2026-03-03 | `scripts/run_forex_pilot_batch.sh` | fixed macOS bash 3.2 compatibility | batch runner crashed with `unbound variable` | stable local launch on user machine | script runs and skips missing CSV gracefully | yes |

## Pending Cleanup Actions
1. Move rejected strategy files to `archive/strategies_rejected/` + manifest.
2. Move obsolete runner scripts to `archive/scripts_rejected/`.
3. Remove archived strategies from `backtest/run_portfolio.py` allowed/import list.
4. Add `docs/REJECTED_STRATEGIES.md` with final rejection reason + latest metrics.
