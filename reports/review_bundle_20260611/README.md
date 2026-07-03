# Review Bundle — Core Trading Strategies

Created: 2026-06-11

This folder contains copied files for an external reviewer who does not have access to the full repository. The live system contains more infrastructure, but these are the core strategy/research files worth reviewing first.

## Crypto Live/Core

- `alt_trendline_touch_v1.py` — ATT1, current main live crypto engine: trendline touch/rejection.
- `alt_inplay_breakdown_v1.py` — inplay/breakdown short engine: support break, failed reclaim or continuation.
- `alt_resistance_fade_v1.py` — ARF1, flat/range resistance fade.
- `alt_support_bounce_v1.py` — support bounce mirror/candidate, currently telemetry/no live risk.
- `impulse_volume_breakout_v1.py` — IVB1 impulse breakout, currently telemetry/no live risk.
- `elder_triple_screen_v2.py` — Elder multi-timeframe candidate, currently off.
- `btc_eth_midterm_pullback.py` — BTC/ETH midterm pullback, currently telemetry/no live risk.
- `liquidity_map.py` — LSR1 liquidity sweep map candidate, not live yet.

## Pair Stat-Arb

- `pair_stat_arb_v1.py` — pair signal/diagnostics.
- `pair_arb_executor_v1.py` — two-leg order intent and pair P&L accounting.
- `validate_pair_arb.py` — realized P&L validator.
- `walkforward_pair_arb.py` — walk-forward validation.
- `fast_pair_research.py` — fast pair research/WF.

## Alpaca

- `equities_swing_active_v1.py` — active swing strategy with trailing/breakeven research.

## Review Notes

- `INDEPENDENT_REVIEW_PACKET_2026_06_11.md` — questions and current internal diagnosis.
- `REVIEW_RESPONSE_2026_06_11.md` — first external-style review response.

## Current Priority

1. LSR1: trend split, symbol walk-forward, then shadow.
2. Alpaca active: walk-forward on 100+ equities including 2022, then paper next to v38.
3. Pair stat-arb: add funding, frozen-beta execution, beta gate, meta-regime gate, then one annual WF on around 20 pairs.

