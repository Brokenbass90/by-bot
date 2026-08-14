# PREREG — Sloped Break/Retest V2

Frozen at: 2026-08-14 before the first V2 economic replay.

Authority: research only. This document cannot authorize shadow, live orders,
risk changes, or promotion.

## Question

Does a causal break of a confirmed 4h sloped pivot line, followed by the first
15m retest and a later 15m structure confirmation, have positive net economics
on liquid crypto majors after next-open execution and full costs?

This is not ATT1. ATT1 fades a touch/rejection of resistance. V2 trades after
the line has broken and the broken line has held on a retest.

## Frozen development contract

- Data window: 2024-03-01 inclusive through 2025-10-01 exclusive.
- Reserved 2025-10-01 through 2026-06-30 holdout: must remain unread.
- Universe: BTCUSDT, ETHUSDT, SOLUSDT, ADAUSDT, LINKUSDT, DOTUSDT,
  AVAXUSDT, SUIUSDT.
- Line timeframe: completed 4h bars.
- Trigger timeframe: completed 15m bars.
- Line: three or four confirmed pivot highs for descending resistance, or
  pivot lows for ascending support. Pivot confirmation requires two bars on
  both sides. Fit error is bounded in ATR and post-fit closes may not have
  already broken the line.
- Break: completed 4h close crosses the frozen line with at least 0.25 ATR
  extension, body fraction at least 0.55, and volume at least 1.20 times the
  prior 20-bar median.
- Retest: first touch within 16 completed 15m bars. The bar must hold back on
  the breakout side. A close through the opposite invalidation buffer kills
  the event.
- Confirmation: not on the touch bar. A later completed 15m bar must close
  through the previous two-bar structure in the breakout direction.
- Entry: next 5m open after the confirmation signal.
- Stop: beyond the retest extreme plus 0.20 of the 4h ATR.
- Targets: 1.5R on 55%, 3.0R on 25%, remaining 20% runner; BE at 1.0R,
  trailing after 1.5R, 24h time stop.
- Sides are reported separately. No higher-timeframe regime or BTC filter in
  this first contract.
- Costs: 6 bps fee plus 2 bps slippage per side, 16 bps round trip.
- Parameter variants: one. No sweep and no winner selection.

## Development verdict

Advance only to a disjoint validation experiment if all are true:

1. at least 80 total trades and at least 30 per side;
2. aggregate net R is positive and PF(R) is at least 1.10;
3. at least five of eight symbols are positive after costs;
4. at least three of four chronological folds are positive;
5. no single symbol contributes more than 40% of positive gross R.

Otherwise the frozen V2 implementation is rejected. That rejects this
contract, not every possible sloped-break mechanism. Any change is V3 with a
new preregistration and disjoint validation window.
