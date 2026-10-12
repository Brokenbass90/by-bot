# Alpaca Dynamic LIVE runtime — October 12 delivery

**DYNAMIC_LIVE_RUNTIME_IMPLEMENTED_ORDERS_OFF / ACTUAL_PAPER_LIFECYCLE_PENDING.**

The isolated quantity-based Dynamic LIVE adapter and native lifecycle integration
are implemented locally. This supersedes the earlier `LIVE_PORT_REQUIRED` local
engineering status. It is not `READY_FOR_LIVE_GO`, a deployed manager or an order
authorization. Current LIVE HALT and the original NET PAPER guard are untouched.

## Delivered behavior

- `research_lab/alpaca_dynamic_live_runtime_v1.py` binds a distinct LIVE source
  book, exact account/host/policy/plan, physical source hashes and the original
  account writer lock. It independently reconstructs the inert intake payload;
  a self-consistent changed quantity, price or stop ID cannot override the plan.
- `scripts/run_alpaca_dynamic_live_v1.py` defaults to read-only. Application
  requires a separate exact owner-GO file, an explicit original LIVE profile
  and source custody. No global env or PAPER credential fallback, HALT clear,
  account flatten, monthly guard bypass, automatic installation or scheduler.
- Every entry/stop/re-arm/exit/replace/cancel attempt is persisted before its
  network operation. Unknown responses are reconciled by exact broker IDs;
  there is no resend/reprice. A reservation without a dispatch cannot buy later.
  A stale native record for the same symbol blocks before BUY.
- Terminal partial BUY quantities receive exact remaining native stop coverage.
  The stop uses the actual fill price and frozen risk distance. Native ownership,
  HWM/floor, DAY re-arm and the unchanged 3.5%/3.5% ratchet planner are reused.
  Dynamic lineage survives native state updates and restart.
- A definitive broker 422 protection rejection triggers one scoped owned exit.
  Unknown stop/replacement outcomes block cancellation/unwind until ownership is
  proven; no blind sell can race an uncertain stop. Partial STOP fills, late stop
  acknowledgement and immediate STOP execution retain actual exit provenance.
- Actual STOP/MARKET/mixed fills retire only the owned native record. Gross is
  separate from net. Fee closure needs a pinned external account/day report plus
  order/cash readback; flatness or pending-fees=0 alone never creates finality.
  Cached finality is explicitly dated. No new slot or entry authority is granted.

Caps remain $487.42 capital, gross 0.70, max4, one entry/session and the selected
OLD slot ceilings. Regulatory/liability reserve reduces spendable cash. Raw IEX
quote CTS is checked; IEX is not described as NBBO. Native/PAPER/monthly sources,
selector, policy, stop parameters and actual broker configuration were not edited.

## Verification and limits

The final targeted command covers the runtime/intake, Dynamic planner/PAPER path,
opening dispatcher and native protection/recovery/ownership/kill components.
**299 targeted PASS**, including **56 new runtime cases**. Full suite:
**4560 PASS /60 FAIL /1 warning**,198.89s. Exact source/test hashes are in
`evidence/alpaca_dynamic_live_runtime_20261012/delivery_receipt.json`.

All 60 failure names match the preceding intake suite. The per-test classification
is in `failure_classification.json`; none was found to materially exercise this
Dynamic LIVE execution path. Three are old Alpaca research/audit contracts (one
missing sibling source), one is a research queue contract, one is a legacy crypto
environment/order-context failure, and 55 are other research/crypto contracts.
The full suite remains **NOT_GREEN**. This is a scoped comparison against the
adjacent published baseline, not proof that every failure predates the project.
The legacy environment case passes alone; its full-suite context issue is retained.

The broker is simulated in these tests; tests are not actual LIVE execution or
an independent edge verdict. Root review found and fixed reservation/dispatch,
lost-stop-response, rapid STOP fill, mutated-intake, unknown replacement and stale
ledger counterexamples. The prior independent reviewer allowance restriction
remains: no replacement/retry and no independent financial signoff claim.

Physical hash custody does not authenticate a fabricated source declaration.
Actual PAPER PASS, writer/manager ownership, OLD terminal/cash/cost sources,
independent LIVE book and exact owner GO still must be bound from real evidence.
No actual production binding/permit was fabricated. This adapter handles one
exact approved plan; it does not approve future replacements or portfolio policy.

## Next actual gate — unchanged schedule

The latest authenticated broker/runtime snapshot remains the **October12
15:41:23 UTC** capture in `ALPACA_OCT13_MONEY_HANDOFF_2026_10_12.md`; no broker,
SSH, service or deployment calls were made during this local implementation.

October13: existing NET guard re-arms at13:30UTC /16:30Cyprus if still held;
owned unwind not before13:35UTC, hard end14:00UTC. Existing read-only observations
at13:32/14:05UTC remain. No extra PAPER entry, restart or schedule extension.

If the actual re-arm/owned exit/cost/finality is clean, immediately assemble the
exact LIVE dossier using this candidate and the fresh independent LIVE sources.
No additional statistical PAPER/Brain/Factory requirement. The next calendar
opening is October14 13:30UTC /16:30Cyprus, conditional on those closures, original
fresh gates and separate owner GO. No execution-date or profit guarantee.

Use `ALPACA_DYNAMIC_LIVE_RUNTIME_RUNBOOK_2026_10_12.md`. KITYOct15/22, closed
BrainV1.1 STOP and Claude research remain separate and unchanged.
