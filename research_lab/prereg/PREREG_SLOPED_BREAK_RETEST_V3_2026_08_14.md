# PREREG — Sloped Break/Retest V3

Frozen at: 2026-08-14 before the first V3 economic replay.

Authority: research only. This document cannot authorize shadow, live orders,
risk changes, or promotion.

## Question

Did V2 reject valid first retests by requiring the touch bar itself to close
back on the breakout side? V3 tests one change only: the first 15m bar may
touch the broken line, then a later completed 15m bar must reclaim it, and only
a still later completed 15m bar may confirm structure and signal an entry.

## Frozen development contract

- Data window: 2024-03-01 inclusive through 2025-10-01 exclusive.
- Reserved 2025-10-01 through 2026-06-30 holdout: must remain unread.
- Universe: BTCUSDT, ETHUSDT, SOLUSDT, ADAUSDT, LINKUSDT, DOTUSDT,
  AVAXUSDT, SUIUSDT.
- Geometry, breakout, invalidation, stop, targets, runner, costs and next-open
  execution are identical to V2.
- Retest change: the first completed 15m bar that reaches the line records the
  touch even if it does not close beyond the V2 hold buffer. A later completed
  15m bar must close beyond that same buffer in the breakout direction. A
  further later bar must make the same two-bar BOS used by V2.
- The original 16-bar retest expiry remains in force and includes the touch,
  reclaim and BOS wait.
- Parameter variants: one. No sweep and no winner selection.

## Development verdict

Advance only to a disjoint validation experiment if all are true:

1. at least 80 total trades and at least 30 per side;
2. aggregate net R is positive and PF(R) is at least 1.10;
3. at least five of eight symbols are positive after costs;
4. at least three of four chronological folds are positive;
5. no single symbol contributes more than 40% of positive gross R.

Otherwise V3 is rejected. A higher trade count alone is not success. Any
further retest, geometry, regime or exit change must be a separately frozen
V4 experiment.
