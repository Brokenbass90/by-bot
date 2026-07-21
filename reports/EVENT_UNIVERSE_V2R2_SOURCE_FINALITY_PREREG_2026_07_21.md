# Event Universe V2r2 — corrected prospective preregistration

Frozen at `2026-07-21T18:18:02Z`, before the V2r2 root or its first observation
existed. This is a timestamp-only correction of the V2 source-finality study; no
outcome was inspected and no threshold, universe, score, horizon, cost, or
selection semantic was changed.

The original V2 run is invalidated because its declared freeze time was later than
its first observation. Its single snapshot remains preserved solely as an audit
artifact and cannot enter any analysis.

V2r2 uses a new spec hash, run root, screen, launch receipt, and snapshot chain. A
row is usable only after `bar_start + 10m <= source_as_of`; any later revision to
the same `(symbol, bar_start)` stops the collector without retry or rewrite. The
run remains public GET-only, research-only, seven-day bounded, non-executable, and
has no credential, account, private API, broker, order, transfer, risk, allocator,
live-router, performance-claim, or promotion authority.
