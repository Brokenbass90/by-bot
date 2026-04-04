# Validation Protocol

Date: 2026-04-02
Purpose: prevent false comparisons, mixed baselines, and misleading portfolio claims.

## Rule 1: No manual "close enough" recreations

If a baseline was validated with a full env overlay file, all future compares must:
- source that exact overlay file
- use the same strategy list
- use the same symbol set
- use the same fees/slippage

If any of those differ, the run must be labeled:
- `exploratory`
- not `baseline`
- not comparable to live without an explicit caveat

## Rule 2: Every reported result must declare its class

Allowed classes:
- `validated_baseline`
- `holdout_compare`
- `recent_window_probe`
- `exploratory`
- `broken_run`

Do not present `exploratory` or `broken_run` as evidence against a validated baseline.

## Rule 3: Apples-to-apples compare checklist

Before comparing two runs, verify:
- same strategies
- same symbols
- same env overlay or explicitly listed diff
- same days/end-date logic
- same execution assumptions
- no cache/data holes

If not, the result is not a like-for-like comparison.

## Rule 4: Broken infrastructure does not count as strategy evidence

These invalidate interpretation:
- missing cached symbol data
- parser failure
- partial env recreation
- stale or wrong symbol universe
- crash rows in autoresearch

First fix the run. Then interpret the strategy.

## Rule 5: Promotion path

Only promote to live when all are true:
- validated baseline pass
- recent-window holdout acceptable
- portfolio contribution acceptable
- server env matches promoted overlay

## Rule 6: Live trust hierarchy

1. Exact validated overlay rerun
2. Holdout compare on same overlay
3. Recent-window compare on same overlay
4. Live diagnostics
5. Exploratory probes

Never invert this order.
