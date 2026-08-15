# ATT1 live-major8 corrected comparison V1

Status: `PREREGISTERED_RESEARCH_ONLY`

## Question

Does the current causal ATT1 contract remain economically positive on the
exact eight-symbol live allowlist after next-open execution, 16 bps round-trip
costs, and the pivot-sequence geometry repair?

## Why this run exists

The prior corrected pre-holdout experiment used `AVAXUSDT` in place of
`LTCUSDT`.  It therefore did not test the exact live allowlist and cannot be
used to decide whether the old narrow-universe result survives the corrected
contract.

## Frozen contract

- Window: `2024-03-01T00:00:00Z` through `2025-10-01T00:00:00Z` exclusive.
- Sealed `2025-10-01..2026-06-30` holdout must not be read.
- Universe: `BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,LTCUSDT,DOTUSDT,SUIUSDT`.
- Signal: short-only `alt_trendline_touch_v1`, 60-minute signal bars.
- Execution: next 5-minute open, stop-first intrabar path handling.
- Costs: 6 bps fee plus 2 bps slippage per side, 16 bps round trip.
- Portfolio: 100 starting equity, 0.75% risk, 1x leverage, three slots.
- Variants: champion geometry disabled and pivot-sequence geometry enabled.
- No parameter search, no symbol substitution, no live or promotion authority.

## Decision rule

This is a contract reconciliation, not a promotion test.  The pivot-sequence
variant is historically viable only if all of the following hold:

1. net R is positive after costs;
2. profit factor is at least 1.05;
3. at least five of eight symbols have positive net R;
4. no single symbol contributes more than 50% of positive net R;
5. at least half of calendar months are positive.

Failure does not stop the existing tiny live canary.  It blocks historical
promotion claims and sends ATT1 to loss-phenotype repair.  Passing still
requires independent audit and future/live evidence; this pre-holdout window
cannot authorize capital.
