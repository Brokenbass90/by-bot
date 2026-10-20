# PUMP4 V1: next execution candidate, ORDERS_OFF

**Evening replacement contract accepted for implementation:** published
`b138735` and request `7b0a961`, verified against origin `7e1ab0b`.
Use **40%/60%, two targets, static stop x4, 168 H1 bars and 137 current symbols**.
The missing helper/producer and universe/mapping questions below are superseded
by the [versioned-contract receipt](evidence/pump4_execution_intake_20261020/versioned-contract.json).
65 OK reference decisions and one unavailable ASTER case are published.
Execution replay, restart parity and broker feasibility remain NOT_RUN.

Historical first intake, preserved with the effective mapping corrected:

Origin `research/fabrika-v1` verified at
`88f42ac16f7baf002b064074f7686bd46996f6a5` on 20 October. The request, readiness
addendum and published result are pinned in the [intake receipt](evidence/pump4_execution_intake_20261020/receipt.json).
The strategy bytes match frozen `2ea8d1f`.

Published Claude result: formal prereg PASS, 66 closed decisions, model net
+0.075R, edge +0.159R, t=2.74. Only 12 are contemporaneous FORWARD, 54 are
OOS_REPLAY; six weekly clusters and model costs limit the strength of the result.
This is a research verdict, not execution acceptance or a new financial GO.

The addendum attributes seven unreproduced decisions to resetting the strategy
between old shadow passes and losing its 24-bar cooldown. Their outcomes remain
UNKNOWN. Codex has not independently reproduced that diagnosis; exact continuous
and restart replay is required under A3, without excluding cases by outcome.

The initial contract mismatch was: the request/addendum say **137** H1 instruments;
the published `research_lab/data/h1/*.npz` inventory contains **138**, also at the
frozen strategy reference. Do not silently choose a subset. A versioned explicit
universe manifest is required before full-universe execution parity. This does
not block work on the state/geometry adapter using pinned individual fixtures.
The research figure 33/50 has a different denominator and is not universe proof.
This source blocker is now CLOSED by the versioned contract and explicit exclusion
of the historical `BTCUSDT_B21.npz` archive; do not use a mutable 138-file glob.

After current Monthly completion, reuse existing Bybit request, dispatch,
native protection, reconciliation and recovery components. The minimal adapter
must retain next-bar-open entry, stop `entry + (sl-entry)*4`, strategy targets,
first fraction **0.40** (corrected by published contract b138735), remaining 0.60
at TP2, 168-bar holding limit and continuous state. The research
ceiling `entry/risk <= 100` does not authorize 100x account leverage.

Execution acceptance remains NOT_RUN: A1 geometry parity; A2 closed-bar causality;
A3 persisted cooldown/history; A4 actual lot/tick/minimum feasibility; A5 bounded
risk including correlated shorts; A6 decision/plan/order/outcome reconciliation.
Also require partial fills, native-stop rejection, lost replies, restart, actual
fee/slippage/funding/margin and gap-over-stop estimates. No new framework.

Research proposes N=5, daily -2r, weekly -3r and review at -6r drawdown. These and
the illustrative r=10 USDT are **unapproved proposals**, not configured limits.
Codex must present an account-feasible small pilot with explicit USDT amounts
for separate owner decision. V2 filters/InPlay/trailing do not enter frozen V1.

Priority: NET safety → finish Monthly → PUMP4 V1. No confirmed TINY date yet;
late October/early November remains a planning window conditional on acceptance
and owner GO. Research code, shadow epochs and financial units were not changed.
