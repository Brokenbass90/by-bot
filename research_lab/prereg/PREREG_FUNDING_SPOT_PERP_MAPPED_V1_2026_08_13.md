# PREREG: funding spot/perp mapped v1

Date frozen: 2026-08-13. Authority: research only, no orders, no risk or
promotion authority.

## Question

Does the previously proposed funding-selection mechanism remain positive after
an exact Bybit spot/perpetual symbol intersection, executable next-open prices,
crossed funding cashflows, and the account's observed taker fees?

## Frozen contract

- Data window: `2023-01-01T00:00:00Z` through but excluding
  `2025-10-01T00:00:00Z`. The reserved 2025-10..2026-06 window must not be read.
- Universe: exact filename/symbol intersection of completed Bybit spot daily,
  linear perpetual daily, and funding archives. No alias guessing.
- This is a current-survivor diagnostic. Point-in-time delistings are unresolved
  and promotion is forbidden regardless of the result.
- Signal: trailing 60-calendar-day cumulative funding through a completed UTC
  day. Select the top three symbols whose trailing funding is positive.
- Execution: enter long spot and short the same-symbol perpetual at the next UTC
  daily open; exit at the UTC daily open 30 days later. Periods do not overlap.
- Cashflow per one unit of spot/perpetual pair notional:
  `spot_return - perp_return + funding_received_by_short - costs`.
- Base costs: 31 bps per completed pair (spot taker 10+10 bps, perpetual taker
  5.5+5.5 bps). Stress costs: 51 bps per pair.
- Comparator: equal-weight all exact-mapped eligible symbols with positive
  trailing funding at the same decision time.
- Variants: one signal contract and two predeclared cost scenarios; no parameter
  search.

## Interpretation

`CANDIDATE_DIAGNOSTIC_ONLY` requires positive stress net annualized return, a
positive selection advantage over the comparator in both chronological halves,
and at least 12 non-overlapping periods. Otherwise `REJECT`. Even a candidate
cannot enter shadow/live until PIT delistings, execution parity, borrow/transfer
constraints, spread/slippage and operational hedge failure are independently
resolved.
