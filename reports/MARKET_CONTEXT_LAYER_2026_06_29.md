# Shared market-context / levels layer — design + migration (2026-06-29)

Author: Claude (central). Recheck/deploy: Codex.
Ships: `bot/market_context.py` (new, tested 9/9), `tests/test_market_context.py`.

## Why
The owner's core thesis is level-based trading (horizontal + sloped, touches,
volume memory). Today each strategy re-derives primitives differently — ATT1 fits
sloped trendlines, ARF2 builds horizontal clusters + HVN/VWAP, others use naive
`max(highs)`/`min(lows)`. That fragmentation is why most strategies "don't see the
market like a trader." This layer gives every strategy ONE consistent view.

## What it exposes (`build_context(rows, atr_value=...)`)
Row format: `[ts, open, high, low, close, volume]`.
- `resistance` / `support` — nearest **horizontal** cluster, with `level`,
  `touches` (how many times tested), `age_bars` (freshness), `dist_atr`.
- `sloped_resistance` / `sloped_support` — fitted **trendline**: `slope`, `r2`
  (colinearity), `level_now`, `dist_atr`.
- `hvns` — volume-at-price high nodes; `vwap`.
- `price`, `atr`.

Primitives are also exported for custom use: `pivot_highs/lows`, `cluster_levels`,
`fit_line`, `sloped_level`, `horizontal_levels`, `volume_hvns`, `vwap`, `atr`.

All logic harvested from the already-validated ATT1 (line fit + R²) and ARF2
(clusters + HVN + VWAP) code, so behaviour matches what already works — just
shared and tested in isolation.

## Design principles
- Pure stdlib, no monolith deps → importable from monolith, strategies, backtests.
- Fail-safe: bad/empty input or non-finite ATR returns `None`s, never throws.
- Deterministic & cache-friendly: pure function of the bars passed in.
- Additive: nothing is rewired yet; strategies opt in one at a time behind their
  own flags, validated through the existing WF gate before any live risk.

## Migration plan (one leg at a time, each through the gate)
1. **ARF1 structured resistance fade** — replace its level logic with
   `build_context(...).resistance` (+ HVN/VWAP confluence). Lowest risk: ARF2
   already proved the cluster approach; ARF1 just adopts the shared version.
2. **ASB1 structured support bounce** — `support` + sloped_support, rejection
   confirm. (ASB1 current impl failed; this is the rewrite the handoffs asked for.)
3. **InPlay retest** — the flagship: volume-in → strong level (shared) → retest
   entry → break on impulse. Consume both horizontal + sloped + HVN.
4. **Elder as a filter** — use `dist_atr` to nearest structure as a context gate
   on ATT1/InPlay rather than a standalone engine.

Each step: wire behind a `*_USE_MARKET_CONTEXT=1` flag → backtest vs current →
multi-window WF → only promote if it does not worsen monthly/DD.

## Acceptance for each migrated strategy (unchanged honest gate)
≥3/4 WF windows positive, PF>1 after 6/2 bps fees, ≤3 red months, red streak ≤2,
maker-entry friendly. Otherwise stays research-only.

## Status
Foundation module built and unit-tested. Next concrete step on your go: wire
ARF1 to consume it (smallest, safest first migration) and run the comparison
backtest. No live behaviour changed by this commit.
