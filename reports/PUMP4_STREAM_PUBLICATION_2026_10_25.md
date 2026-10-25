# PUMP4 — per-symbol publication without waiting for full census

25 October 2026. **COMPONENT_PASS / UNSELECTED / ORDERS_OFF / TINY_NOT_READY.**

## What was fixed

Production evidence showed0/132 decisions published within the60s entry window,
even though93/132 source captures were timely. Publication proxy was84.544–230.339s.
The existing collector waited for the entire137-symbol archive before the supervisor
processed any completed instrument. It also yielded futures in input order.

The same collector now publishes a hashed immutable metadata prefix, yields each
fsynced symbol via `as_completed`, and calls the existing supervisor intake on the
main thread. Each instrument gets a context/source-bound immutable processing
receipt. Full137 coverage remains a separate later final seal; early receipts
explicitly say coverage_complete=false. Finalization verifies and reuses those
receipts without changing original decisions, first-observed times or mode.

No frozen strategy/intake change: seed/cooldown/closedH1/decision IDs/epochs and the
60s entry gate remain. Same journal source hash, frozen producer and137 universe.
The supervisor reuses an already verified replay snapshot instead of rebuilding it
again for epoch validation. One identical fictional warm fixture made6replays
before vs5after, identical journal bytes and decision ID. Its0.152s vs0.117s is
one local synthetic sample, not a production speedup guarantee or market evidence.

Partial captures remain preserved and blocked from blind recollection that hour.
New tests prove early durability before a120s-delayed final census; restart and
final archive reuse; no bootstrap/late promotion; per-symbol completion despite an
earlier slow instrument; context/source mutation and post-verification file races
fail closed. Root found/fixed two integrity gaps during implementation; both have
RED→GREEN regressions. Callback receipt no longer asserts0strategy calls when an
external causal DATA callback ran: countUNKNOWN(null), callback-used explicitly.

## Verification and exact candidate

**253 local / same253 VPS PASS**,14test modules,106packaged files,46imports,
68fixture receipts; network denied (VPS additionally unshare--net),0fallback,
0skips/errors/failures,0realbrokerrequests/writes. Not506 independent broker checks.
Final source material:
`5deafc9fdd232bdc1e63148e0a3718cc680236d26f7815280b0e1de8d9d9baf1`.
Candidate:
`/opt/bybot-research/pump4-server-orders-off-20261023/candidate-5deafc9fdd232bdc`.
Earlier31e5b2d69df47eab is inert/superseded after the provenance-only correction.

One actual verified astra/high independent critical review:0Critical/Important;
27targeted testsPASS. The same reviewer confirmed the small provenance followup.
Actual model/effort verified from rollout turn_context, not only requested settings.
[Evidence, exact manifests and receipts](evidence/pump4_stream_20261025/).

## What is NOT claimed

**The new candidate is NOT SELECTED. Actual next-H1 publication latency is still
UNVERIFIED. No financial GO or TINY_READY.** All existing production units/configs,
DATA collector/epoch/journals, original Bybit lock818853 and Monthly remain unchanged.
Existing PUMP selected PID2865120/NRestarts0/OFF and config83a32143…3306 were rechecked.
Monthly selected unit SHA9d94467d…32cc1d is unchanged. No original wrapper/GO was run.

The current DATA root is still:
`/opt/bybot-research/pump4-server-orders-off-20261023/candidate-9c6901a65a66e035/app/.private/pump4-supervisor-v1`.
Bindingf1a32a29…38a00, referenced by selected ORDERS_OFF config:
`candidate-30677ce61f137272/owner-review-health-v3/runner.json`,
SHA83a32143606b37c0ce8410ddd20067aaad8840dfb2b5d445556d132375803306.
Do not edit that binding or signed sources in place: it would cause source drift.

## Exact next gate — continue here, not a new executor/audit

1. Build a bounded ORDERS_OFF DATA/config handoff with explicit rollback. Preserve
   exact old per-symbol journal bytes/epochs/cursors/cooldown/observations/history;
   no reseed, retiming, evidence overwrite or change to frozen intake source pin.
   Rebind the existing trusted consumer to reviewed sources without a second writer.
   Verify active PID/lease/flat account and absence of admissions/attempts before
   any operational owner rebind; no financial activation implied.
2. Observe one actual NEW H1: distinguish source receipt from durable publication
   completion. Prove timely paths with actual immutable records; late/unavailable
   symbols remain blocked. Do not widen60s or claim a synthetic cycle as actual.
3. Complete source→freshaccount→fees/funding/rounding/sizing/admission→existing
   lifecycle ORDERS_OFF, then one exact TINY risk/cost/stop/40-60/restart packet.
   Only separately authorized financial scope can permit actual PUMP orders.

Monthly is already personally selected and idle-cycle accepted; no more Monthly
source/budget/strategy changes. Future30Octselection/2Novfresh trading checks stay.
Queue: Monthly custody → PUMP → Polymarket → KITY. The broader goal remains Brain,
Factory, classical strategies and intelligent portfolio management in the existing
canonical roadmap, without automatic AI trading authority or a duplicate framework.
