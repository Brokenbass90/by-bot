# Monthly: posted legacy-cost bridge and durable loss admission

**Component PASS; complete Monthly activation remains BLOCKED.** Base1096957.
Source material **7628c2a9bd798c9366c9e6e80fca163a431fa99972ac3c185785694300b3ba9e**.
Owner budget/BUY-loss-latch preparation terms are confirmed in the private owner
dossier. No executable LIVE scope/GO, service cutover or personal exit was issued.

## DONE

- Existing cost producer accepts an explicit owner-pinned **already terminal**
  legacy NET seal. It verifies account, complete quantity, identities, terminal
  orders and pre-anchor timestamps. The seal is bound into the new cash anchor
  and scope/config; it is rechecked after the final clock GET before BUY.
- Full account activity, account-day allocations and cash reconciliation remain.
  Posted NET costs affect cash/other cash; Monthly net excludes legacy costs.
  NET remains OFF_PROTOCOL, outside Monthly custody. Unknown fills still reject.
- Standing Monthly loss admission now latches durably. A fsynced observation
  precedes fresh PnL reads; incomplete observations, corrupt markers and failed
  stop publication block future BUY across restarts/grant renewal. Only a SAFE
  observation clears its own checkpoint. No automatic reset or forced sale.
- Recovery, native protection and owned-ticket reconciliation continue. A known
  incomplete recovery/accounting state rejects before starting loss observation;
  ownership/accounting are re-read after it begins. Loss is also observed on ticks
  without new signals. Existing account lock and one book/manager are retained.
- Fresh personal NET exit envelope comparison plus independent review: exactly
  one service source pin proposed; plan/date/entry/quantity and all other fields
  unchanged. Local proposal only, not installed/armed/executed.

## TESTED

| Acceptance | Result |
|---|---|
| Exact isolated local | **209 PASS**,542.949s |
| Same exact isolated VPS | **209 PASS**,488.363s |
| Package |53sources,16test files/helpers,40actual imports,0checkout fallback |
| Full synthetic E2E |2receipts per run: actual production CLI source/entry/protection/lost replies/restart/rotation; pending-fee replacement/finality |
| Independent review |One bounded component review, same-worker targeted fixes;27targeted PASS overlap root tests |
| VPS independent GET/hash |Source/test/receipts verified;93prior static pins unchanged; candidate UNSELECTED |

Both exact runs deny networking; real broker requests/writes **0**. These are the
same cases repeated across environments, not418independent observations.
[Receipts, manifests and reproduction](evidence/monthly_transition_20261021/README.md).

Review caught failed latch publication being forgotten after price recovery;
write-ahead observation fixed it. E2E caught a known stop-response recovery gap
being permanently latched; prevalidation fixed it. The initial superseded run was
cancelled with that regression and is not counted as PASS. A targeted source
mutation test also required rechecking the legacy seal after the final clock GET.

## REMAINING / EXACT BLOCKER

**Legacy pending-fee classification is NOT implemented.** A terminal seal proves
ownership/closure, not that fees have posted. The prior pending calculator would
subtract all account pending fees from Monthly net. A replayed fixture showed a
legacy penny could falsely trigger the durable Monthly loss latch.

Now a legacy-bearing estimate with unposted account fees rejects explicitly:
`MONTHLY_PENDING_FEE_LEGACY_ATTRIBUTION_UNRESOLVED`, before returning Monthly PnL
or creating loss-observation markers. Before any Monthly exit, positive legacy
liabilities still reject `MONTHLY_PENDING_FEE_LIABILITY_UNCLASSIFIED`. Existing
owned-only bounded-pending support remains accepted. No absence-as-zero inference.

**Next code gate:** source-backed pending classification for initial legacy
handoff and mixed account days; reserve/check all account liabilities while only
Monthly costs enter its loss metric. Regression already captures the false-latch
case. Preserve complete activities, actual posting lag, pinned tariff/calendar/
assets, freshness, restart and cash/anchor reconciliation. Do not remove the
foreign-fill guard or weaken unknown handling. This engineering does not wait for
market dates, Brain, new research or another general launch-intent question.

Final executable scope/config hashes remain unfrozen until this blocker closes.
Actual NET terminal seal, scheduler retirement/rollback proof,30Oct completed
source and2Nov fresh market/broker facts are separate future gates. They cannot
be fabricated now. The old personal exit launcher is not advertised as ready.

## OTHER LANES / CLAUDE DELTA

[c80712c dependency check and all11immutable external-review links](BRAIN_PRODUCTION_DEPENDENCY_CHECK_2026_10_21.md):
**NO_IMPACT** on the checked Monthly, frozen PUMP4, KITY execution and selected
NET manager closures. Generic structural/FX callers do have behavior dependencies.
`pump_exhaustion_unwind_short_v1` is **not** frozen PUMP4 V1. No research merge.

PUMP4 producer65/65 replay remains accepted; executor/continuous restart/native
stop/actual TINY feasibility remain NOT_RUN. It is the next money executor,
without waiting for2Nov or InPlay/V2. KITY stays SPENT/ORDERS_OFF; this work grants
no new crypto authority. No research/KARTA/judge edits or Claude messages.

26Oct: final packet READY_FOR_OWNER_REVIEW or precise BLOCKED;28Oct: PUMP4 executor
acceptance or precise BLOCKED;30Oct: Monthly technical/source decision;2Nov is
the conditional original rotation window. No profit or BUY date is promised.
