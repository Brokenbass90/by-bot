# Liquidity Hunter V1 Spec — 2026-04-30

## Goal

Build a crypto sleeve that trades stop-hunt / liquidity-sweep behavior without trusting visual chart intuition.

First version is OHLCV-only and research-only:

- local high/low liquidity pool from recent 5m bars
- sweep beyond the pool
- close back inside the range
- rejection wick and volume confirmation
- stop beyond the sweep wick

## Why This Is Worth Testing

Many crypto moves do hunt clustered stops around obvious highs/lows. The edge is plausible, but it must be proven by:

1. annual standalone backtest
2. additivity versus the current live canary
3. walk-forward / OOS stability
4. live shadow counters before any money

## Implemented First Slice

- Strategy: `alt_liquidity_sweep_reversal_v1`
- Autoresearch spec: `configs/autoresearch/liquidity_sweep_reversal_v1_probe.json`
- Strategy state: research-only, not wired to live bot or allocator

## First Smoke Results

- Strict 30d BTC/ETH smoke: compiled and ran, but produced `0` trades.
- Relaxed 90d BTC/ETH/SOL smoke: `49` trades, `PF=0.700`, `net=-2.53%`, `DD=4.67%`.

Interpretation: the pattern can generate trades, but the first relaxed slice is negative. The next step is parameter research by side/regime, not live promotion.

## Next Data Upgrades

- liquidation-cascade feed / liquidation map as confirmation
- open-interest drop/spike filter
- funding extreme filter for crowding
- order-book imbalance near swept level if exchange data is reliable

## Promotion Gate

Do not deploy this strategy from a pretty chart or a standalone pass only.

Minimum promotion path:

- 360d standalone: PF >= 1.18, net >= +5, DD <= 10%, enough trades
- portfolio additivity: improves or at least does not degrade canary v2 PF/DD/red-month count
- WF-22: majority stable enough to avoid recent-window overfit
- one week shadow mode in live before risk > 0
