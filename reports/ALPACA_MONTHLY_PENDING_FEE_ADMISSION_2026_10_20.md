# Monthly: bounded pending-fee admission, 20 October 2026

Scope: finish the existing patch against `543c137`, ORDERS_OFF. This is a
component acceptance, not autonomous Monthly activation or financial authority.

## Delivered

The existing cost collector/producer can explicitly emit an immutable
`PENDING_NOT_FINAL` estimate for executed, owned fills whose known account-day
assessments have not all posted. Default finality remains strict. Missing activity
is not evidence of zero cost. Unknown fees, foreign fills, conflicting cash,
unsupported tariff or insufficient existing reserve reject admission.

The existing Monthly native binding replays that evidence against its one book,
current account and authorized tariff. It subtracts the account's unposted known
fees once from conservative realized net. Cash admission keeps the existing
`liability_reserve_usd` once; this patch neither chooses nor increases a reserve.
The finalizer never accepts an estimate as final net PnL.

The one manager refreshes costs after rotation and before each new ticket.
Protection/recovery precede accounting. A late accounting error blocks new risk;
it does not disable maintenance. Source freshness is checked after replay and
again after the final broker clock GET before dispatch. An expired proof leaves
the durable reservation without sending a buy.

LIVE opt-in would require a new owner scope with
`pending_fee_admission=SOURCE_CLASSIFIED_WITHIN_EXISTING_RESERVE_V1` and the exact
`pending_fee_protocol_sha256`, in addition to existing custody/GO/source checks.
Old grants cannot accidentally enable this behavior. No such grant was created.

## Verification

Exact material: `bd267c75380f9bc8ad1f82175d89e963043ec6c4d561bb02a7e63f3d7bd74faa`.
51 source files, including the previously omitted `equities_earnings_filter.py`.
The selector, strategy, universe and ratchet rules were not changed.

Local isolated exact-package suite: **274 PASS / 0 failures / 0 skipped**,
283.65 seconds; 39 imported source modules, zero checkout fallback, sockets denied.
35 cases cover the new pending-fee path. The complete frozen58 rehearsal uses
the actual selector, not a substituted selection.

| Failure / transition | Observed acceptance |
|---|---|
| Incomplete day, known late assessment | Explicit pending estimate; strict finality still rejects |
| Posted cents / partial executed fills | Reconciled against existing raw captures; posted fees not reserved twice |
| Unknown fee, changed cash/book/ownership, excess assessment | Reject; no new order |
| Unknown liability even with no exits or all exits final | Reject; no strict-success bypass |
| Wrong LIVE tariff / old owner scope | Reject |
| Slow replay / delayed final clock | Reject stale proof; reservation retained, no duplicate dispatch |
| Supported REST metadata/timestamp representation | Existing execution-identity checks pass; economic changes reject |
| Frozen source → rotation → pending fees → replacement | Full memory-broker E2E PASS |
| Lost native-stop reply → restart → repeated tick | Recovery; no duplicate entry |
| Late posted fees | Existing finalizer closes prior exit; prior estimate unchanged |
| Multi-symbol opening | Cost refresh observed before each of four fixture entries |
| Rollback with owned exposure, uncertain dispatch or pending accounting | Refuses rollback and retains owned manager; flat rollback idempotent |

One independent `gpt-6-astra/high` review found four defects: liability shortcut,
tariff self-pinning, proof aging, and supported broker representation mismatch.
All four were fixed and independently rechecked: **34 PASS, 1 E2E deselected**.
The final 274-case suite includes the complete E2E after these fixes. No second
whole-change or independent server review is claimed.

Server exact-package suite: **274 PASS / 0 failures / 0 skipped**,277.80 seconds;
all four E2E receipts present (basic lifecycle, two cycles/one fixture grant,
automatic delayed-cost finality, rotation with pending fees). Separate network
namespace and socket denial;39 imports/zero fallback. Independent post-run GET
confirmed all51 source and18 test hashes,93 protected static pins unchanged,
and no selection of the candidate by existing financial/observer units.
The uploaded candidate is inert and unselected. No system unit, deployed NET manager, SHOP
timer, financial profile, HALT, live book or owner permission is changed.

## Still required for the autonomous release

1. Wire the existing manager's applying tick and automatic cost callback into
   the single production entrypoint, with pinned configuration. The installed
   `run_alpaca_monthly_cycle_v1.py` still exposes source/preview only. The memory
   rehearsal does not prove that applying production CLI exists.
2. Complete that entrypoint's exact NET handoff and rollback acceptance. Current
   tests establish custody/no-adoption and disabled rollback behavior; they do
   not migrate the actual NET position or create authority to exit it.
3. Present the concrete bounded standing packet: actual reserve adequacy,
   tariff/source pins, attempt/notional/loss ceilings and revocation. Future or
   unknown charges are not guaranteed by the executed-fill estimate.
4. Future facts: actual 30 October close/source/selection and fresh account,
   ownership, native protection and permission at the 2 November window. These
   cannot be replaced with fixture receipts today. A permitted window may still
   yield CASH/NO_SEND.

No calendar wait is needed for items 1–3. They remain the current Money P0.
PUMP4 V1 follows Monthly; its research intake is recorded separately. No KITY,
Weekly, SHOP, InPlay or trailing change is included in this patch.

Evidence: [package, tests and receipts](evidence/monthly_pending_fee_20261020/).
