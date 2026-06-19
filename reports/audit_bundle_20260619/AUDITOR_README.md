# Auditor evidence index - 2026-06-19

This bundle contains the complete evidence currently available for the crypto
portfolio. It does not claim 6-12 months of live history: the live journal has
40 closed trades from 2026-04-05 through 2026-06-18.

## Live evidence

- `live_trade_events.jsonl`: complete available live journal, 112 events and
  40 closed trades.
- `STRATEGY_EVIDENCE_2026_06_19.md`: aggregate PnL, PF, win rate, t-statistic,
  direction split, and research inventory.
- Effective runtime at the latest server heartbeat:
  - live-risk: `flat=0.30x`, `range=0.25x`;
  - shadow/scan-only with zero risk: ATT1, Bounce, Breakdown, IVB1, Midterm;
  - account equity approximately 121 USDT, risk per trade 0.44%, maximum three
    simultaneous positions, no configured no-entry UTC hours.

## Research evidence

- `server_results/range_live_results.csv`: 216-combination live-parity sweep
  for the current live `RangeStrategy`; 0 promotion passes.
- `server_results/elder_results_partial.csv`: 541 completed Elder variants;
  all failed.
- `server_results/inplay_v3_results_partial.csv`: superseded pre-fix InPlay
  evidence. Do not use for promotion.
- `server_results/range_ars1_results_partial.csv`: early ARS1 sweep evidence.
- `range_ars1_r003/` and `range_ars1_r004/`: trade streams and summaries for
  the first positive ARS1 candidates.
- `../ARS1_NEXT_OPEN_VALIDATION_20260619.md`: corrected next-open validation.
  Best candidate: 108 trades, net +16.61 on 100 starting equity, PF 1.682,
  max DD 6.68. It fails the monthly gate because 2025-10 and 2025-11 are red.
  The control-plane comparison reduces PF from 1.68 to about 1.46.

## Execution and cost model

- Promotion research now uses `--entry-on-next-open`: a signal formed on a
  closed bar is filled at the following bar open.
- Fee and slippage inputs are per side. Standard directional research uses
  6 bps fee plus 2 bps slippage per side, or 16 bps round trip.
- Breakdown research currently uses 10 bps fee plus 10 bps slippage per side,
  or 40 bps round trip.
- If stop and take-profit are both reachable inside one bar, the simulator
  resolves stop first.
- The generic directional engine exposes historical funding to a strategy but
  does not debit periodic funding cashflows from portfolio PnL. Results for
  positions held across funding timestamps are therefore incomplete until a
  funding cashflow ledger is added.

Relevant implementation:

- `backtest/engine.py`
- `backtest/portfolio_engine.py`
- `backtest/run_portfolio.py`
- `scripts/run_strategy_autoresearch.py`

## Geometry and look-ahead status

Geometry implementation: `bot/chart_geometry.py`.

`find_pivots()` confirms a pivot with `right` later bars. That is delayed
confirmation, not future leakage, only when every supplied row is already
closed before the decision timestamp. `strategies/inplay_retest_v3.py` now
enforces this contract by removing incomplete/future rows and using the latest
fully closed entry-timeframe bar as the trigger. The entry-timeframe ATR is
used for retest distance; structure ATR remains limited to level clustering
and level-based exits.

Regression channels and horizontal clusters operate only on the row slice
passed by the strategy. Any other caller of `chart_geometry` must enforce the
same closed-row contract.

## Current strategy source paths

- InPlay retest: `strategies/inplay_retest_v3.py`
- Elder: `strategies/elder_triple_screen_v2.py`
- Pump fade: `strategies/pump_fade_v2.py`
- Breakdown: `strategies/alt_inplay_breakdown_v1.py`
- Range candidate: `strategies/alt_range_scalp_v1.py`
- Geometry: `bot/chart_geometry.py`

Current next-open research specifications:

- `configs/autoresearch/inplay_retest_v3_level_retest_repair_v2.json`
- `configs/autoresearch/elder_ema50_force_canonical_v1.json`
- `configs/autoresearch/pump_fade_v5_bear_window_v1.json`
- `configs/autoresearch/breakdown_recent_bear_window_v2_entry_quality.json`
- `configs/autoresearch/range_scalp_v1_annual_repair_v3.json`
- `configs/autoresearch/vwap_mean_reversion_v1_annual_repair_v2.json`

## Known evidence gaps

- No 6-12 month live/shadow trade stream exists for every strategy.
- Historical funding cashflows are not yet included in generic directional
  portfolio PnL.
- Current server health catalog is stale and should not be treated as the live
  strategy roster; the heartbeat `strategy_runtime_config` is authoritative.
- Correlation, Monte Carlo, and allocation calculations should wait for
  strategy-level OOS trade streams produced by the current next-open queues.
