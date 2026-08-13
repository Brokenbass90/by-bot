# Alpaca protection challenger V2

Frozen before outcome access on 2026-08-13. Research only; no order, live,
promotion, or capital authority.

## Question

Can two executable contract repairs improve the clean-962 daily proxy without
inventing a new selector: anchor the initial 2 ATR stop to the actual next-open
fill, then refuse a market entry when the observed opening gap is above 2%?

## Fixed arms

1. `current_contract`: stop anchored to signal close, no positive-gap cap.
2. `entry_relative_stop`: stop anchored to next-open adverse fill, no gap cap.
3. `entry_stop_gap2`: entry-relative stop and no entry when open is more than
   2% above the completed signal close.

The 2% gap gate is implementable as a quote check plus marketable-limit/IOC
policy. It is not a retrospective skip based on the day's high or close.

## Frozen measurement

- Same clean 962 files, v38 selector, weights, 70% target exposure, monthly
  decisions, profit ratchet and 21-day re-entry block as V1.
- Base 5 bps per side and stress 10 bps per side.
- All three arms are reported; no parameter sweep or champion substitution.
- Diagnostic improvement requires both base and stress: lower daily max DD,
  no lower annualized return, PF no lower, and at least 30 realized exits.
- PIT membership, sector completeness, corporate actions, XNYS calendar and
  15-minute live-manager parity remain blockers regardless of result.
