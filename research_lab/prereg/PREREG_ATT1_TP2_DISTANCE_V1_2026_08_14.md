# ATT1 TP2 distance challenger V1

Frozen before the run on 2026-08-14. Research only; no live or promotion authority.

## Question

Does moving the second target from 2.5R to 1.8R improve the repaired ATT1
Geometry V2 runner after costs? Historical causal exports reach TP2 in only
about 1-2% of trades; this test measures whether that distance leaves too much
runner profit exposed to retracement.

## Arms

1. Champion: TP1 1.2R / 55%, TP2 2.5R, breakeven and trailing at 1.0R.
2. Challenger: unchanged except TP2 is 1.8R.

The 1.8R challenger is the midpoint between TP1 and the current TP2 rounded to
one decimal place. It was not selected from a parameter sweep. No other exit,
entry, universe, risk, cost, or geometry field may change.

## Frozen contract

- universe: BTC, ETH, SOL, ADA, LINK, DOT, AVAX, SUI perpetuals;
- window: 2024-03-01 through 2025-09-30; sealed holdout remains unread;
- signal: H1, execution: next M5 open, stop-first intrabar processing;
- costs: 6 bps fee plus 2 bps slippage per side;
- max positions: 3; short only; Geometry V2 enabled;
- compare net R/trade, PF, monthly breadth, TP1/TP2/trailing reasons and drawdown.

## Decision

The challenger is promising only if net R/trade and PF both improve, it does
not add more than two red months, and improvement is not concentrated in one
symbol. Any result remains research-only and needs separate validation before
shadow or live use.
