# ATT1 pivot-sequence challenger V1

Frozen before the run on 2026-08-13. Research only; no live or promotion authority.

## Question

Does requiring the three short-resistance pivots to be actual non-increasing
lower highs improve the unchanged ATT1 short champion? A descending regression
slope alone can hide a final higher high, as in the BTC live loss on 2026-08-13
(`64477 -> 63690 -> 63994.4`).

## Arms

1. Champion: unchanged ATT1, Geometry V2 disabled.
2. Challenger: same strategy and costs, but block a signal when any consecutive
   resistance pivot is higher than the preceding pivot.

No tolerance sweep and no parameter search. One binary mechanism test.

## Frozen contract

- universe: BTC, ETH, SOL, ADA, LINK, DOT, AVAX, SUI perpetuals;
- window: 2024-03-01 through 2025-09-30, excluding the sealed holdout;
- signal timeframe: 60m, execution: next 5m open;
- costs: 6 bps fee plus 2 bps slippage per side (16 bps round trip);
- max positions: 3; short only; exact contiguous public-cache input required;
- report net R as net PnL divided by recorded initial risk, not dollars alone.

## Interpretation

- If the handle or outputs are indistinguishable, fail closed as an invalid test.
- Promising: challenger improves net R/trade and PF without removing more than
  70% of trades, and the direction is not carried by one symbol/month.
- Rejected: net R/trade or PF worsens materially, or remaining breadth collapses.
- Any promising result still requires a separately frozen time/symbol validation
  and prospective observation. This run cannot change live ATT1.
