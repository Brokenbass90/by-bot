# Higher-TF Cache Prewarm Report — 2026-04-29

## What Was Done

Created:

- `scripts/refresh_cache_higher_tfs.py`

The script writes real `.cache/klines/{SYMBOL}_{INTERVAL}_{START}_{END}.json` files for higher timeframes:

- `15`
- `60`
- `240`
- `1440`

Unlike the first Claude sketch, this script does not import `fetch_klines()` from `smart_pump_reversal_bot.py`, because that live helper only fills an in-memory cache. The new script uses `backtest.bybit_data.fetch_klines_public()` and then writes the backtest cache format that `backtest/run_portfolio.py` expects.

## Smoke Test

Command:

```bash
python3 scripts/refresh_cache_higher_tfs.py --symbols BTCUSDT --intervals 60 --days 30 --end 2026-04-25 --polite-sleep-sec 0.1
```

Result:

- saved `720` bars
- file created: `.cache/klines/BTCUSDT_60_1774483200000_1777075200000.json`

## Important Correction

The “flat/breakdown_v2/elder have zero trades because `.cache/klines` lacks 60m/240m/1440m files” diagnosis is not automatically true for `backtest/run_portfolio.py`.

`backtest.engine.KlineStore` aggregates higher timeframes from the loaded base 5m candles:

- `15m`
- `60m`
- `240m`
- `1440m`
- `10080m`

So if a strategy is run through `run_portfolio.py`, absence of separate higher-TF `.cache/klines` files should not by itself cause empty higher-TF data. A separate higher-TF cache is useful for scripts that directly request those intervals, but it is not the primary fix for portfolio backtests.

## Full Prewarm

A full 540d prewarm was started, but stopped after inspection showed it was likely spending Bybit request budget on a non-blocking issue for `run_portfolio.py`.

Current exact higher-TF cache count after smoke:

- at least `1` higher-TF file exists locally (`BTCUSDT_60_...`)

## Verdict

Keep `scripts/refresh_cache_higher_tfs.py` as a utility, but do not treat higher-TF prewarm as the main repair path.

Next debugging step for 0-trade strategy runs should inspect:

- whether the strategy is actually using `run_portfolio.py` and `KlineStore`
- whether `ALLOW_LONGS`/`ALLOW_SHORTS` flags are wired
- whether signal timeframe env vars match strategy config parsing
- whether strategy thresholds are too strict
- whether the current symbol set has enough completed aggregated bars inside the requested window
