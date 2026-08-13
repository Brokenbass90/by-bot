# PREREG: funding spot/perp mapped v2

Frozen 2026-08-13 after V1 failed data forensics. V1 showed a false +909%
period because ZEC spot was `1.16` while the same-timestamp perpetual was
`47.57`. V1 remains immutable evidence and is not a result to optimize.

V2 preserves the complete V1 hypothesis, universe intersection, 60-day funding
ranking, top-3, next-open execution, 30-day hold, comparator and 31/51 bps cost
scenarios. It adds one data-integrity rule only: a symbol is executable for a
period only when absolute spot/perpetual basis is at most 5% at both entry and
exit. A larger discrepancy is quarantined and reported, not traded. No other
parameter changes are permitted.

The same V1 decision rule applies. The run is current-survivor research only;
PIT delistings, real spreads and operational hedge risks remain blockers even
if the diagnostic survives.
