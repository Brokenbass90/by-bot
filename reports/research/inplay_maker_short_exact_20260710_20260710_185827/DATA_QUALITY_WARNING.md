# Data-quality warning

This result is hypothesis-generating, not promotion evidence.

- The frozen 360-day source universe included `ADAUSDT` and `SUIUSDT`; both have a shared maximum gap of `1,033` M5 bars (about 3.6 days) under the strict preflight used on 2026-07-10.
- The original maker research runner tracks portfolio occupancy with per-symbol candle indices. Those indices are not comparable across symbols after a data gap, so cross-symbol slot accounting can be distorted.
- The attractive short-only stress result therefore requires a clean-universe replay with timestamp-based occupancy plus independent-symbol additivity before any shadow or money decision.

No live orders or risk changes were possible in this run.
