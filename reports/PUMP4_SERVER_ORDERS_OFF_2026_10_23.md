# PUMP4 — actual server ORDERS_OFF cycle, 23 October 2026

**SERVER DATA COMPONENT PASS; FINANCIAL RUNNER/HANDOFF STILL BLOCKED.** One
unselected server process now joins real H1 captures, existing causal intake,
authenticated account GET and sizing diagnostics. The existing financial owner
adapter is called by the thin `owner_cycle` integration point in memory tests;
the actual GET-only process cannot dispatch financial orders.

## Actual server result

[Server receipt](evidence/pump4_server_20261023/actual-server.json):
137 frozen symbols,136 actual H1/source/intake checks PASS,136 duplicate decisions
on repeated immutable-source replay. HFTUSDT remains explicitly unavailable; no
replacement or change of universe. The current bootstrap produced **zero signals**.
Thus this run proves no actual signal-specific TINY sizing or live execution.

Account capture used9 GETs: **8 authenticated and1 public ticker GET**. Account
was flat. Raw timestamps, HTTP bodies/hashes, complete pages, public archive seal
and account capture remain private on VPS. Seed/history is bootstrap, not new
prospective evidence. Restart replay uses the original capture cutoff, not a
claim that old data is currently fresh. Symbol-specific mode/funding/fees/lot
checks remain fail-closed when a real signal exists.

The original physical owner is still `kity-execution-micro-owner.service`,
PID2734312 at the recorded check. It holds the original account lock inode818853.
The server process reported **EXISTING_OWNER_BUSY_NO_SECOND_WRITER** and never
constructed a financial owner, took over its lease or stopped/reconfigured it.
This is a concrete ownership blocker, independent of NET commissions.

## Code, acceptance and review

- `research_lab/pump4_server_cycle_v1.py`: immutable archive → existing per-symbol
  intake, restart/source-lineage checks, account/source diagnostics and existing
  owner integration call. No default POST, credential loader or financial grant.
- `scripts/run_pump4_orders_off_v1.py`: one explicit GET-only server process,
  reusing the known source-pinned credential binding and existing transports.
  It has no LIVE/dispatch/GO option; default execution makes no requests.
- `tests/test_pump4_server_cycle_v1.py`: restart/no duplicate or reseed, altered
  raw archive rejection, exact owner integration through the full memory entry/
  native-stop/40–60 exits/flat-cost-pending cycle, no-request default, no dispatch
  mode and changed historical lineage rejection.

**184 tests locally and the same184 on VPS PASS**, zero errors/failures/skips,
85 files,32 imports, no checkout fallback. The suite includes prior lost-response,
partial-fill, restart, native-stop and risk-latch tests. Those failure injections
use the memory exchange, not real broker mutations.
Material: `15a9d213a79c44ae0aef4766903459d56c31659e27134a4ec95225d5f11b043c`.
[Local](evidence/pump4_server_20261023/local-acceptance.json),
[VPS](evidence/pump4_server_20261023/vps-acceptance.json),
[sources](evidence/pump4_server_20261023/source-manifest.json).

One verified **gpt-6-astra/high** review found a provenance defect: a changed,
re-sealed historical seed could reuse an old decision while claiming the new
archive. Root reproduced RED, compared incoming historical overlap against the
immutable seed/accepted prefix, then passed the final184 tests in both environments.
No reseeding, silent history replacement or second review was used.
[Review disposition](evidence/pump4_server_20261023/review.json).

Two reporting minors remain explicit: the aggregate DATA_COMPONENT_PASS label
alone is insufficient if source_intake_pass=0; and the current raw receipt's
`authenticated_get_requests` field counts all9 account calls. This report uses
the correct8authenticated+1public split and actual136 checked sources.

[Independent final readback](evidence/pump4_server_20261023/preservation.json)
confirms all64 selected NET files and the legacy HALT unchanged, no new financial
unit or GO. No order was sent on either broker.

## Remaining before TINY_READY

1. Implement and accept the **financial** server wrapper using this existing
   account-owner adapter and original physical verifier. The new server CLI is
   deliberately GET-only and cannot become financial through a flag.
2. Prepare the exact original-owner retirement/handoff and single-writer unit/
   profile/source configuration; verify recovery without changing the spent KITY
   authority. Do not run alongside the existing owner or invent another lock.
3. Prove timely closed-H1 → permitted entry admission through that wrapper.
   Today's historical bootstrap is not a prospective outbox or permission to
   enter an old signal. Validate current per-signal tick/lot/minimum/cost/funding
   feasibility; no missing/unknown item becomes a synthetic PASS.
4. Present the complete single-lifecycle TINY packet, actual scope/alert/recovery
   evidence and risk/cost assumptions. Allocation50/gross30/reserve20/R1/day2/
   week3/DD6 remain unapproved proposals, not a guaranteed loss bound.

No PUMP4 financial GO is requested before that packet. Alpaca fee finality is
not a dependency. Polymarket/KITY/Brain/Factory were not expanded in this cycle.
