# CODEX HANDOFF 2026-07-08

## Live Money Truth
- Bybit is flat on the latest local/server mirror available to Codex. Live-money crypto sleeve remains only `ATT1 short r001 risk_mult=0.10`; no second crypto sleeve is live.
- ADAUSDT incident remains recorded as: profitable manual close, but not a clean autonomous ATT1 win. Root issue was runner/TP visibility and execution continuity after restore; runner heartbeat/health fixes are deployed in code path from the 2026-07-07 work.
- Alpaca LIVE fresh read-only snapshot from `2026-07-08 06:06 UTC`: equity `$490.80`, cash/BP `$192.23`, account active, trading not blocked. This is about `-$4.10` vs the `$494.90` funded base, i.e. roughly `-0.8%` drawdown.
- Alpaca positions: `ABBV -$1.96`, `BAC +$0.65`, `GE -$2.84`, `PANW -$0.75`, `XYZ -$0.07`. Broker-side simple stops exist for `ABBV/BAC/GE/PANW`. `XYZ` has an accepted market sell, not a stop; likely queued to flatten on next US open. Recheck after market open.

## Overnight Results So Far
- Broad crypto MRB/naive "pila" remains failed: z18/z24 variants are negative (`PF≈0.84`, `0/4` positive folds). Do not promote a generic z-score basket.
- FX/CFD is not capital-ready. Local H1 strict coverage still blocks some native tests; M5 multi-strategy exploration did not produce a clean promotion row. Treat FX/CFD as research-only until data coverage and OOS pass.
- Level-memory sweep/reclaim remains the closest crypto candidate. Prior exploration had a pulse (`83` trades, `+11.81R`, `PF 1.30`, but only `2/4` folds). It now has a strict OOS prereg runner.
- Cascade real-liq "0 trades" is not treated as dead. New runner mode adds sparse-liquidation window intensity and condition diagnostics so future zero-trade runs show the binding condition.

## Code Changes This Session
- Added `scripts/run_level_memory_oos_prereg_20260708.py`.
  - Frozen params from prereg: `respect_min=0.65`, `lookback=48`, `rr in {1.2,1.6}`.
  - Reports coverage, base/stress results, concentration, 40/8 causal selector, holdout symbols, and BTC-regime split.
  - No network, no orders, no live risk changes.
- Updated `scripts/run_cascade_real_gate.py`.
  - Default legacy mode unchanged.
  - Added `--trigger-mode window_v1` with window intensity trigger and rolling-mean/absolute liq spike logic.
  - Added `--diag` output with per-condition true rates.
  - Added `run_symbol_window_v1()` and tests.
- Updated `tests/test_run_cascade_real_gate.py`.
  - New coverage for sparse liquidation spike and condition diagnostics.
- Validation:
  - `python3 -m py_compile scripts/run_level_memory_oos_prereg_20260708.py scripts/run_cascade_real_gate.py`
  - `.venv/bin/python -m pytest tests/test_run_cascade_real_gate.py tests/test_cascade_reversal.py` -> `15 passed`.
- Refreshed local AI context with `python3 scripts/build_ai_full_context.py --quiet`.

## Running Screens
- `screen=level_memory_oos_prereg_20260708`
  - log: `logs/level_memory_oos_prereg_20260708/run.log`
  - output dir printed in log, currently `reports/research/level_memory_oos_prereg_20260708_20260708_062304/`
  - expected: heavy run; if holdout symbols are missing, verdict should be `NO_PROMOTION / blocked_by_data`, not a silent substitution.
- `screen=cascade_window_v1_real_20260708`
  - log: `logs/cascade_window_v1_real_20260708/run.log`
  - output: `reports/research/cascade_window_v1_real_20260708/`
  - expected: even if trades remain zero, inspect `diag.csv` for binding condition.
- `screen=web_local_position_embed_20260707b` remains detached for local web.

## Next Morning Checks
1. Check `reports/research/level_memory_oos_prereg_20260708_*/summary.md` and `verdict.json`.
   - Promotion rule: only all prereg steps pass -> `lm_sweep_reclaim_v1` shadow/risk=0.
   - If blocked by missing holdout cache, backfill holdout set: `NEAR,INJ,TIA,SEI,ARB,OP,APT,RUNE`.
2. Check `reports/research/cascade_window_v1_real_20260708/summary.md`, `summary.json`, and `diag.csv`.
   - If zero trades, use diag to identify whether funding/OI/direction/liquidity is binding.
3. Recheck Alpaca after US open:
   - whether `XYZ` accepted market sell filled;
   - whether every remaining position has broker-side protection;
   - whether equity drawdown remains within canary noise.
4. No Bybit risk increase until there are at least two validated sleeves and clean autonomous exits.

## Do Not Do
- Do not delete old strategies blindly.
- Do not promote MRB broad basket.
- Do not promote Inplay maker on near-miss PF.
- Do not enable `RUNNER_EXCHANGE_TP_ENABLE=1` without owner approval.
- Do not raise Bybit/Alpaca exposure because one day is green or red.

## 2026-07-08 Midday Update Before Pause
- VPS read-only check: `/root/by-bot` is at commit `f7ed011`, `bybot.service=active`, and `runtime/portfolio_health.json` is being written. This includes the runner-heartbeat and portfolio-health fixes (`06c12d3` + `f7ed011`). The newer local commits above that are research/docs orchestration, not required for immediate live safety.
- Bybit direct REST on VPS: `open_position_count=0`; `runtime/live_positions.json` also has `count=0`, `dry_run=false`, `trade_on=true`. Current crypto live money remains only ATT1 short r001; no second crypto sleeve promoted.
- FX coverage blocker is resolved for strict H1 research on `EURUSD,GBPUSD,USDJPY`: use `data_cache/forex_1h`, `--interval-min 60`, `--min-coverage 0.98`, `--max-gap-bars 24`. `XAUUSD` remains blocked until cleaner/full backfill.
- Started full FX H1 grid locally:
  - `screen=fx_native_h1_full_grid_20260708`
  - log `logs/fx_native_h1_full_grid_20260708/run.log`
  - outdir `reports/research/fx_native_h1_full_grid_20260708`
  - command uses pairs `EURUSD,GBPUSD,USDJPY` and setups `trend_pullback,session_breakout_retest,session_range_fade,round_level_sweep`.
  - First log line confirms `EURUSD coverage=0.995732`, so the harness is now using the correct H1 gate.
- Started local keep-awake screen for the pause:
  - `screen=prevacation_keepawake_20260708`
  - command: `caffeinate -dimsu -t 432000`
  - Note: this helps while the Mac is powered/open; closing the laptop into sleep can still stop local screens.
- `level_memory_oos_prereg_20260708` is still running and heavy; latest log is at `simulate_base_start rr=1.2`. This is the closest crypto sleeve candidate, but it has no promotion until the prereg OOS verdict completes.
- `cascade_window_v1_real_20260708` completed with `combos=0`. The new `diag.csv` is useful: the binding conditions are mostly `oi_ok`/direction/liquidity rarity, not only the old timing bug. Cascade remains a data-accumulation branch, not a next live sleeve.
- Alpaca last checked snapshot remains a small canary drawdown around `-0.8%`; broker-side stops were present for the main positions. Recheck after US open for the accepted `XYZ` sell and current stops.

## What To Check First After Return
1. `tail -n 120 logs/fx_native_h1_full_grid_20260708/run.log` and inspect `reports/research/fx_native_h1_full_grid_20260708/`.
2. `tail -n 120 logs/level_memory_oos_prereg_20260708/run.log` and inspect latest `reports/research/level_memory_oos_prereg_20260708_*/verdict.json`.
3. On VPS, confirm `open_position_count=0/expected`, `portfolio_health.json`, and Alpaca stops before any new risk change.
4. Only if level-memory or FX grid gives a clean prereg PASS: wire to `shadow/risk=0.0` first. No direct canary/live promotion from this pause.
