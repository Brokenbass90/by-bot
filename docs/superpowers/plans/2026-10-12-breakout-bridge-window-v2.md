# Breakout source-window bridge V2 implementation plan

> **For agentic workers:** execute inline using executing-plans/TDD. Continue
> the current recovery checkout; preserve V1/strategy/level source byte identities.

**Goal:** correct the independently reported full-aggregate versus lookback-window
hash mismatch, with a source-verified orders-OFF version and no strategy tuning.

**Architecture:** separate V2 module preserves V1 immutable receipt/validation
structure. Require exact raw closed M5 prefix through persisted plan boundary;
recompute full level/event/plan aggregates, then hash only the level's recorded
window. Both scopes become explicit V2 receipt evidence. Existing V1 remains
available unchanged; no automatic substitution in Claude's running shadow.

**Tech stack:** existing Python/dataclasses/pytest, frozen aggregation and MTF.

**Spec:** owner-transmitted Claude defect at V1 line464; level_snapshot_v1
lines810/877 intentionally hash lookback only. Research e22c0e0 local / e2d668c
origin at intake. No judge, outcomes, PnL analysis or new research criteria.

## Global constraints and rulings

- New bridge only; frozen strategy/config/fees/risk/entry/exit untouched.
- Alpaca original NET PAPER opener/guard, LIVE HALT/caps, Mac/VPS processes untouched.
- Brain one-shot is spent BLOCKED; do not rerun or change any pinned code/source.
- Ruling: V2 requires `raw_closed_m5` explicitly, because hashes in persisted
  state alone cannot demonstrate membership of the window in the full aggregate.
  Claude must select V2 and supply the saved prefix in a versioned adapter update;
  Codex will not patch his checkout or silently reinterpret old receipts.
- Ruling: V2 receipt schema/identity is distinct. Unchanged MTF plan identity and
  entry/risk geometry are retained; execution-plan identity changes with evidence.
- Bounded replay is signal/bridge mechanics only on already parity-consumed AVAX
  Aug12–Oct11 data; never simulate exits/read future outcomes or rerun a judge.
- Original reviewer quota restriction remains: root review only, no quota retry.

## Review focus

Long H1 and H4 windows; modified M5 data outside/inside lookback; mismatched raw
state hash; altered window hash with recomputed outer identities; future/open
tails/gaps; foreign provider/full aggregation hash; duplicate/acknowledged plan;
deterministic reconstruction after restart; unchanged stop/entry/economic contract.

### Task1: reproduce and source-bind V2

Files: tests/test_event_long_mtf_execution_bridge_v2.py,
bot/event_long_mtf_execution_bridge_v2.py.

- [x] RED: long-history fixture produces a valid plan but V1 rejects it.
- [x] Implement V2 using preserved V1 validation structure, explicit M5 prefix,
  full aggregate provenance and exact recorded lookback window checks.
- [x] GREEN: short/long history, tamper/future/gap, receipt/restart tests.
- [x] Reuse original execution simulator only on synthetic test prices to check
  unchanged entry/stop/cost/exit semantics. No real-history outcome simulation.

### Task2: exact bounded source-only replay and delivery

- [x] Pin local research manifest/source files, verify original core parity.
- [x] Reproduce old AVAX rejection and verify V2 conversions on exact saved
  decision prefixes; preserve state/receipts/compact hashes, no acknowledgement
  inferred from conversion and no Mac shadow change.
- [x] Targeted V1/V2/aggregation/levels/MTF/state/execution regressions and root
  review; durable terminal report/runbook/canonical TOP.
- [x] Scoped commit/push and actual remote verification; foreign diff preserved.
  Implementation2502d8e published and matched actual ls-remote; publication receipt
  is evidence/breakout_bridge_v2_20261012/publication_receipt.json.

Stop at BRIDGE_V2_ENGINEERING_PASS or exact BLOCKED. No prospective acceptance,
profitability verdict, broker readiness or money authority follows from this fix.
