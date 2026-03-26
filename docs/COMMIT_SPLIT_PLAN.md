# Commit Split Plan

Purpose: keep history reviewable and stop generated artifacts from drowning real code changes.

## Package 1: Core Research Runtime
- `backtest/bybit_data.py`
- `backtest/engine.py`
- `backtest/portfolio_engine.py`
- `backtest/run_portfolio.py`
- `strategies/signals.py`
- new `strategies/*.py` that are imported by the runtime
- `custom_indicators.py` only if a committed strategy imports it

## Package 2: Forex / Equities Isolated Pipelines
- `forex/`
- `scripts/run_forex_*`
- `scripts/fetch_forex_*`
- `scripts/forex_*`
- `scripts/run_equities_*`
- `scripts/fetch_equities_*`
- `scripts/update_forex_combo_state.py`
- `scripts/update_equities_combo_state.py`
- `scripts/export_forex_live_filters.py`
- `scripts/export_forex_demo_env.sh`

## Package 3: Operator Rules And Control Files
- `configs/inplay_soft_live.env`
- `configs/battle_filter_rules.json`
- `configs/battle_candidates.json`
- `scripts/build_battle_snapshot.py`
- `scripts/run_battle_snapshot.sh`
- hand-written docs such as `docs/HANDOFF_20260306.md`, `docs/RD_FOCUS_RULES.md`, `docs/RD_CLEANUP_PLAN.md`

## Do Not Commit As Code
- `docs/*_latest.{csv,txt,json,env}`
- `docs/*_backup_*.csv`
- `backtest_runs/`
- `data_cache/`
- `backtest_runs_old_*.tgz`
- `share_main_strategy/`
- `share_main_strategy.tar.gz`

## Practical Order
1. Commit Package 1 first. Runtime must build without relying on generated docs.
2. Commit Package 2 second. Market-expansion tooling stays isolated from crypto core.
3. Commit Package 3 last. Rules, wrappers and handoff docs can then point to the committed runtime.
