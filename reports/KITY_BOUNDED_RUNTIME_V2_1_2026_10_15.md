# KITY bounded owner V2.1 — October 15

**V2.1 INSTALLED / ORDERS OFF / STATIC READY.** Separate exact money GO is absent.
Same approved50bps/600000ms,215gross/15immediateall-intrigger/30minutes/20.3%
reference rounding; accepted execution overshoot and research firewalls unchanged.
The old intent `7aa4504d…145cd` expired at18:30:11.877Cyprus without GO/order/selection
and is not extended or transferred. Its earlier READY receipt is dated history.

## Actual implementation and deployment

Author review found **PLANNING_DEFECT**: the outer expiry check preceded the
parent owner's potentially slow final custody check. The regression
`test_expiry_during_final_custody_check_is_rechecked_at_transport_boundary`
failed before the fix (DID NOT RAISE; synthetic callback was reachable).
V2.1 adds a final entry fence to the callback immediately before SignedPostOnce
barrier/signature/transport invocation, after parent custody. No slow GET/CAS
lies between that fence and the transport call. Durable intent remains before
wire; proven local no-wire is recorded; existing barriers stay UNKNOWN and are
never resent. Exit/cancel management is independent of the entry expiry.
Full relevant suite after this fix: **240 targeted PASS**, root-only review;
full repo suite not run. No policy/threshold/math was retuned.

New immutable app `/opt/bybot-research/kity-micro-owner-20261015/app-v2-1-bounded`,
config `runtime/config-v2-1-bounded.json`, SHA256
`6d420ec075ebf3c23f97386de3b16c36020e5135b46d6ab36f2634e5095f54b2`; unitSHA256
`08b7f04e50d961770656f6a50eedb1fe9831516106dc52b3248de0ed06e1671d`. Same unit `kity-execution-micro-owner.service`,
PID **2188843**, NRestarts **0**, active/defaultORDERS_OFF.
Original lockinode **818853** held; second lease refused.16sourcepins verified.
The original V1 and earlier V2 source kits/configs remain immutable.
Original ffeb plan/GO/SQLite/terminal fourpins remain unchanged.

A temporary existing entry fence was created after confirming no selection/
POST. The controlled upgrade again required authenticated flat/open/recent
orders/executions zero before stop, quiescent under the original lock and after
startup. Only the exact operator-owned temporary fence was removed by hash CAS
once the replacement was ready. It did not clear an owner HALT or grant money.
No bybot/web restoration, cron/ATT1/LIQ/Alpaca/Claude mutation. Original old
writers stay inhibited. Unit source/config changes are versioned and dated.
Installation receiptSHA256 `49bacf85c27b055b7f24e735b411bf00a5c3a7ccb82d351e85d26fde8ea1bb50`.

## Remaining operational action

All engineering binding is complete. Prepare one **new** reference intent and
perform its existing GET-only rehearsal through this daemon. This is a new
version's readiness proposal, not a retry of the consumed ffeb experiment or an
extension of the expired V2 hash. Keep every earlier source/receipt intact.
Only a separate literal human GO on that new exact hash may create a selected
experiment and dispatch. No auto-entry, follow-up timer or repeating loop added.
A new proposal's immutable ten quantities/price bands/expiry must be shown before
asking GO. Actual GO then consumes it before exactly one fresh capture and one
derived plan; mandatory existing gates run again per leg.

Use `research_lab.kity_micro_bounded_owner_v2` from app-v2-1-bounded with the
config/hash above. Controls: PREPARE_BOUNDED, REHEARSE_BOUNDED, GO_BOUNDED, KILL.
Stored permission preserves the literal intent GO; internal bridge exact-plan
token is not represented as another human approval. Selected store stays
`runtime/experiments-v2/<intent_id>`, original journal remains read-only.

Recovery/rollback details from KITY_BOUNDED_RUNTIME_2026_10_15.md still apply,
but its old app/config/PID/intent/GO command are superseded. Use only V2.1's
explicit --rollback path resolving the selected journal; never V1 old-journal
rollback for a selected new experiment. No rollback to old writers was executed.

Sanitized deployment/source pins: evidence/kity_pricing_intent_20261015/physical_binding_v2_1.json.
