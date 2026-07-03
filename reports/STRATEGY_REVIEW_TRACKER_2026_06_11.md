# Strategy Review Tracker — 2026-06-11

Purpose: track which strategy families have independent/code review coverage, what must be fixed, and which strategies still need review before promotion.

## Reviewed / Needs Fixes

### ATT1 — `strategies/alt_trendline_touch_v1.py`
Status: reviewed, critical code fixes applied locally, needs re-review/backtest before deploy.

Critical fixes:
- slope-sign logic: signed slope helper plus separate `abs_slope_pct` threshold — applied 2026-06-11;
- reset no-signal reason at the start of `maybe_signal` — already present, covered by review;
- unused wick variables removed — applied 2026-06-11;
- resolve docs vs implementation mismatch: regression trendline vs actual pivot-to-pivot line.

Important follow-ups:
- Wilder RSI;
- cooldown by bar/time, not call count;
- optional candle-color requirement;
- minimum ATR/liquidity filter.

### Inplay / Breakdown — `strategies/alt_inplay_breakdown_v1.py`
Status: reviewed, critical code fixes applied locally, needs targeted re-check/backtest before deploy.

Fixes:
- preserve detailed `_regime_ok` no-signal reason instead of overwriting it — applied 2026-06-11;
- `tp1_rr` now uses configured `rr * tp1_frac`, capped only by full RR — applied 2026-06-11;
- legacy wrapper handles sync or async `maybe_signal` — applied 2026-06-11;
- document/review armed-signal overwrite behavior.

### ARF1 — `strategies/alt_resistance_fade_v1.py`
Status: reviewed, critical code fixes applied locally, needs re-review/backtest before deploy.

Critical fixes:
- `es_prev` should be previous EMA (`closes[:-1]` or EMA series), not `closes[:-6]` — applied 2026-06-11;
- unify signal price and entry price source — applied 2026-06-11, entry geometry now uses closed signal bar `cur`;
- fix `_env_bool` empty-string behavior — applied 2026-06-11;
- document TP2 buffer for shorts and assert TP2 remains below entry.

Important follow-ups:
- parameterize TP1 distance factor;
- add volume confirmation;
- minimum SL distance / ATR filter;
- clarify 5m vs signal-TF naming.

### Elder — `strategies/elder_triple_screen_v2.py`
Status: reviewed, needs design decision, then re-review.

Critical fixes/design choices:
- Screen 3 is currently close-confirmed breakout, not canonical stop-order entry;
- fix Force Index EMA initialization;
- consider default `trend_require_hist_sign=True`;
- make body/close-rank filters optional or clearly document modified Elder logic;
- short close-rank threshold should be stricter if kept.

### Alpaca Active Swing — `strategies/equities_swing_active_v1.py`
Status: reviewed twice, critical code fixes applied locally, still needs wide walk-forward.

Fixes:
- Wilder RSI — applied 2026-06-11;
- robust handling of invalid market relative-strength data — applied 2026-06-11, RS required now fails closed without enough market history;
- always return full metric fields from `score_symbol` — applied 2026-06-11;
- validate input shape: close series, not OHLC rows;
- keep `base_score` when applying quality multiplier.

Local verification:
- `python3 -m py_compile` on modified strategy/test files — pass;
- direct local execution of `tests/test_strategy_review_fixes.py` + `tests/test_equities_swing_active.py` test functions — 14/14 pass.

Validation gate:
- walk-forward on 100+ equities, including 2022 bear market;
- 20+ paper trades, 4 weeks, zero protection incidents before real capital.

## Reviewed / Research-Only

### LSR1 Liquidity Hunter — `bot/liquidity_map.py`
Status: reviewed, best new candidate, not live yet.

Required before shadow/live:
- split results by with-trend vs counter-trend sweeps;
- symbol-level walk-forward so the basket is selected on IS and validated on OOS;
- test pool-to-pool and TP1+runner exits against current 2R.

### Pair Stat-Arb
Files:
- `strategies/pair_stat_arb_v1.py`
- `strategies/pair_arb_executor_v1.py`
- `scripts/validate_pair_arb.py`
- `scripts/walkforward_pair_arb.py`
- `scripts/fast_pair_research.py`

Status: reviewed, lowest priority of the three research candidates.

Fixes before next verdict:
- funding accounting;
- frozen beta-weighted legs;
- beta stability gate;
- regime/meta gate;
- annual WF on roughly 20 pairs.

## Not Yet Reviewed / Needs Review

High priority:
- `strategies/alt_support_bounce_v1.py` — support-bounce counterpart to ARF1.
- `strategies/impulse_volume_breakout_v1.py` — IVB1; previously promising as package additive, needs code review and WF.
- `strategies/btc_eth_midterm_pullback.py` — BTC/ETH midterm sleeve.
- `configs/alpaca_v38_hybrid_top4_candidate.env` + `scripts/equities_alpaca_paper_bridge.py` — v38 execution/protection review before real money.

Medium priority:
- `strategies/alt_slope_break_v1.py` — ASB1 slope-break, off live.
- `strategies/alt_horizontal_break_v1.py` — HZBO1 horizontal breakout, off live.
- `strategies/alt_bear_regime_continuation_v1.py` — BRC1 bear continuation candidate.
- `strategies/micro_scalper_v1.py` — micro scalp, fee-sensitive, not live-ready.
- `strategies/pump_fade_smart_v1.py` / pump-fade family if still considered.
- `strategies/liquidation_cascade_entry_v1.py` — only after liquidation data collector is trusted.
- `strategies/funding_rate_reversion_v1.py` — funding/carry candidate, must include realized funding.

Low priority / only if revived:
- retired/archive strategies;
- RMR1 / TPB1 after poor initial candidate tests;
- grid strategies until they produce enough trades in honest tests.

## Smart Leverage / Risk Overlay Needed

Leverage should be a portfolio-risk module, not a fixed exchange leverage setting.

Inputs:
- strategy edge / live-vs-backtest confidence;
- realized volatility and ATR;
- current drawdown;
- regime confidence;
- correlation between open positions;
- liquidation buffer;
- per-sleeve caps and max same-direction exposure.

Outputs:
- per-trade risk multiplier;
- max notional/leverage per sleeve;
- hard liquidation-distance guard;
- automatic deleveraging during red-month/DD regimes.
