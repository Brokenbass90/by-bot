# KITY_EXECUTION_MICRO_LIVE_V1 — separate execution experiment

October15 owner directed preparation of parallel micro execution, without
changing frozen research. **Design + actual read-only feasibility delivered;
money bounds undecided, no money authority or sender delivered.** This is not
`KITY_EXECUTION_MICRO_LIVE_READY` and not a canary promotion.

## Scope and authority

The experiment would test the actual whole Oct15 independently reconstructed
five-long/five-short Bybit basket. It cannot drop, substitute or pad instruments.
Source/C2 receipts remain unchanged. Research ranking, universe, hold seven
days, costs and C1–C3 remain unchanged. Separate probe duration/kill rules, if
approved, belong only to this execution experiment; it is never presented as a
completed KITY strategy trade. No need to wait for a new strategy PnL sample to
build the executor. Equally, no execution probe authorizes strategy promotion.

Use existing Decimal book/depth primitives, hash-bound evidence, existing
execution identifiers/accounting and an isolated durable journal. Do not adapt
ATT1's short-only single-position coordinator into a ten-leg authority by
changing its existing tables or production profile. No parallel monolith,
research framework, autonomous LLM or account-wide flatten.

## Measured sizing, not an invented dollar amount

The single GET capture is sealed in the accompanying evidence manifest. BTW
requires quantity10 with step10, about21.84USDT at the observed ask. The smallest
common reference target is21.84290USDT/leg. Existing floor rounding produces
210.266660USDT gross but a20.27% LTC leg shortfall. This is a **diagnostic floor**,
not an approved equal-weight implementation. Choosing the cheapest individual
minimum for each symbol (about77.72 gross) is not an equal-notional basket.

Discrete alternatives, calculated without PnL or ranking adjustment:

| Maximum per-leg floor-rounding shortfall | Target/leg | Gross at recorded depth |
|---|---:|---:|
| Unspecified, venue-floor diagnostic |21.84290|210.266660|
|5% (unapproved)|66.45856|658.062380|
|2% (unapproved)|87.37160|870.433860|
|1% (unapproved)|374.0932|3733.106280|

These alternatives do not silently select a new research weight rule. Exact
equal USD fills are not generally available on independent price/quantity grids;
live fills also differ from these recorded reference prices. Owner must select
an explicit execution rounding policy before a faithful executable basket is
declared. The current record is expired for dispatch.

## Required owner decisions before money implementation can be finalized

1. Absolute aggregate/per-leg notional caps and permitted rounding residual.
2. Maximum planned loss **including costs**, emergency action and experiment
   duration/deadline. A short timed round trip can be proposed, but is not
   silently substituted for the research seven-day hold.
3. Account/margin policy. Current UTA2 account uses REGULAR_MARGIN and stored
   leverage3 on LTC/BNB,10 on other selected symbols. Submitted quantity controls
   gross exposure; stored10x does not multiply a specified quantity by10. Still,
   cross collateral is not a guaranteed tiny loss budget. Do not change modes,
   leverage, transfer collateral, add credentials or claim isolation implicitly.

At observed prices the cheapest diagnostic basket's flat-price round trip is
about0.25588USDT (fees plus spread), not a future upper bound. A1% simultaneous
adverse move on all positions adds about2.10267USDT;5% adds10.51333USDT before
changed exit prices/costs. A stop/loss trigger is an action threshold, not a
guaranteed worst-case loss. A short leg has no finite theoretical loss bound;
cross margin can expose shared collateral. No exact owner GO text is issued
until these material fields are concrete and the complete executable plan exists.

## Execution contract to implement after the bounds are concrete

- Seal one experiment/account/session/expiry/source/C2/ten-leg plan, plus exact
  code/config pins and money caps. Distinct `EXECUTION_MICRO_LIVE` ledger and
  `KXM1-<12hex>-E00..E09` entry namespace; exits `X00..X09`. LinkID uniqueness
  alone does not establish ownership or prevent manual symbol interference.
- Prove original account writer coordination and exclusive ownership of all ten
  symbols. Current flat linear-USDT readback is not proof that another writer
  cannot enter later. Preserve foreign orders/positions and old admission policy.
- Before the single attempt: fresh selected-account identity/permissions,
  wallet/liabilities, complete scoped positions/orders, exact instruments/fees,
  all-ten book depth and common source-CTS≤2s, clock bound and loss/cost funding
  reservation. Do not waive any missing value or substitute zero.
- Durable reservation then durable per-leg send intent **before** transport.
  One entry attempt/leg using bounded price IOC; no retries, repricing,
  averaging, scaling, session transfer or additional experiment. A network
  timeout is `DISPATCH_UNKNOWN`, not a rejected order.
- For known partial/reject: stop new entries; reconcile all attempted legs and
  executions, cancel only owned live residual orders where proven. Unwind the
  actual owned filled quantity with reduce-only exits. No sell against an
  uncertain or unrelated position. A failed unwind remains explicit exposure
  requiring owned recovery and owner notification, never a clean terminal.
- On complete basket: verify actual fills, protection/kill mechanism and frozen
  probe deadline. On protection failure perform the approved scoped safety
  action; do not continue the experiment unprotected.
- Restart: acquire the same original ownership lock, replay the isolated journal
  and reconcile signed order/execution/position history before action. Never
  infer no order from a single empty realtime reply. Unknown entry sends are
  never automatically resubmitted. Reconcile duplicate executionIDs exactly.
- Exit/finality: own positions zero, all own orders terminal, deduplicated actual
  fees/funding/cash reconciliation. Pending fee/funding is UNKNOWN, never zero.
  Preserve kill/recovery authority while any owned exposure/uncertainty exists.
  One experiment only; no new start until terminal finality and separate GO.

## Firewall and verification

Execution records cannot be appended to Claude's shadow/opportunity/judge
datasets. They have `purpose=EXECUTION_ONLY_NOT_RESEARCH`, separate identifiers,
and explicit false C1/C2/C3/edge/promotion flags. No PnL-based retuning or KEEP/KILL.
No writes to Claude files/processes, liquidation sources, Alpaca or ATT1.

Implemented now: source reader, replayable sanitized account/depth/fee dossier,
pure minimum/rounding geometry and clock checks. Tests verify invalid numbers,
minimum/maximum bounds, no quantity increases, discrete frontiers against an
exhaustive breakpoint oracle, explicit missing CTS and group stale/future clocks.
These are not order/partial/restart/protection/finality tests. Those lifecycle
tests must accompany the later integrated sender; none is claimed PASS here.

Alpaca Oct15 remains P0 and frozen: fresh preflight before16:15Cyprus, separate
exact GO, arm before16:29, one opening attempt16:30–16:35 with the existing latest
start boundary. No micro engineering in its opening critical path.
