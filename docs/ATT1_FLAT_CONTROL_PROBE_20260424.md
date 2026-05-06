# ATT1 + Flat Control-Plane Probe 2026-04-24

## Goal

Design the next narrow live canary around `ATT1 + flat_arf1` and identify which control-plane gates can be relaxed without losing quality.

Inputs:

- Horizon: `390d`, end `2026-04-21`
- Window: `30d` stitched dynamic annual
- Base risk: `0.005`
- Active sleeves: only `att1` and `flat`; all other sleeves paused/zeroed
- Router: dynamic historical router unless explicitly noted

Generated probe artifacts:

- `backtest_runs/att1_flat_control_probe_20260424_071111/report.md`
- `backtest_runs/att1_flat_control_probe_20260424_074249/report.md`
- `backtest_runs/att1_flat_control_probe_20260424_080434/report.md`

## Baseline

`router_current`: current router, current hard regime gates.

- Return: `+2.15%`
- PF: `1.055`
- Trades: `314`
- Max DD: `6.05%`
- Negative months: `6`

This is better than the failed relaxed four-sleeve package, but too thin to promote as a finished live package.

## What Passed

Best clean relaxation:

`router_att1_bear_soft`

- Change: keep dynamic router; only relax the ATT1 hard-disable in `bear_trend`
- Return: `+2.98%`
- PF: `1.0682`
- Trades: `405`
- Max DD: `6.05%`
- Negative months: `6`

Best narrow research candidate:

`router_att1_bear_bear_allocator_flat`

- Change 1: keep dynamic router; only relax ATT1 hard-disable in `bear_trend`
- Change 2: flatten allocator global risk only in `bear_chop` and `bear_trend`
- Return: `+4.75%`
- PF: `1.0925`
- Trades: `405`
- Max DD: `6.05%`
- Negative months: `6`

This is the best next narrow package from the tested set.

## What Failed Or Stayed Research-Only

Do not relax `flat` in `bull_trend` yet:

- `router_flat_bull_soft`: `+1.84%`, PF `1.0463`, DD `6.04%`
- It underperforms baseline and hurts the first bull-trend window.

Do not freeze the full ATT1+ARF1 winner universe:

- `fixed_current`: `+2.41%`, PF `1.0497`, DD `7.92%`
- `fixed_regime_allocator_flat`: `+4.32%`, PF `1.0665`, DD `8.53%`
- Fixed symbols improve some windows, but worsen stability and drawdown.

Do not flatten allocator risk in all regimes as the first move:

- `router_allocator_flat`: `+3.40%`, PF `1.0737`, DD `6.26%`
- It worsens the known bad `bull_chop` window `2025-05-26 -> 2025-06-25`.

## Proposed Next Live Canary

Stage 1, safest:

- Package: `ATT1 + flat`
- Router: dynamic, current profiles
- Health: `alt_trendline_touch_v1=OK`, `alt_resistance_fade_v1=OK`; all other crypto sleeves `PAUSE`
- Relax: `ENABLE_ATT1_TRADING=1` in `bear_trend`
- Keep: `ENABLE_FLAT_TRADING=0` in `bull_trend`
- Keep current allocator global risk by regime
- Do not add `bounce1`, `impulse`, `breakdown`, `range_scalp`, or `inplay_breakout`

Stage 2, after Stage 1 shadow/canary confirms live behavior:

- Same package and router
- Keep ATT1 enabled in `bear_trend`
- Raise allocator global risk only for `bear_chop` and `bear_trend` to `1.0`
- Keep `bull_chop` allocator global risk at current `0.9`

## Remaining Risk

The hard remaining problem is not bear-side control-plane anymore. It is the `bull_chop` drawdown window:

- `2025-05-26 -> 2025-06-25`
- Baseline and best narrow candidate both keep this around `-3.01`, PF about `0.681`, window DD about `4.37%`

Next repair target: a bull_chop guard for ATT1+flat, not a broader sleeve package.
