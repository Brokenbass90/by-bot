# Execution-only Alpaca and two baseline engineering tasks

Owner brief: current Oct9 operational incident → prepare opening before Monday;
no LIVE change, no fake PAPER acceptance, no ATT1/KITY rescue or new judge.
This is implementation of the supplied bounded scope, not new research approval.

- [x] P0: reuse DynamicBook and the exact PAPER adapter. Add a preloaded,
  one-shot opening controller with static preparation by T−15m, readiness by
  T−1m, fixed five-minute window, timestamped fresh/reserve/adapter phases and
  hard pre-dispatch budgets. A missed deadline is terminal before reservation.
  Persist intent to execute before invoking the adapter; ambiguous invocation
  is never replayed. Existing owned maintenance remains separate.
- [x] P0 verification: offline exact planner/PAPER integration, slow capture,
  future/stale sources, changed static files, restart, uncertain dispatch,
  partial fills and no LIVE endpoint. No broker lifecycle PASS from fixtures.
  Preserve Oct9 reserved plan; unresolved source/handoff is an explicit blocker.
- [x] P1: freeze two original strategy sources, wrappers only, compare exact
  baseline results on synthetic existing fixtures, causal closed-data contract,
  explicit fee/slippage/funding inputs and immutable opportunity receipts.
  Inventory validation independence from metadata; no outcomes/judge/trend edits.
- [x] One independent financial review, one targeted fix pass, scoped commit /
  push / remote verification and one compact canonical result.

Readiness vocabulary: local controller/parity PASS is engineering only. Actual
READY_TO_DISPATCH requires current source/ownership mappings, a valid source
book/handoff, session-specific closed-data ranking and a separately authorized
PAPER attempt. It neither implies broker PAPER PASS nor LIVE GO.
