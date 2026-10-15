# KITY micro — owner loss policy V2 and durable monitor

**Local policy/monitor: verified. Monetary status: BLOCKED_EXECUTION / orders-OFF.**

The owner's direct reply to `call_6b8bf99c313243c1b85f5c3504a5c292` makes
$15 an obligatory immediate all-in exit threshold and explicitly accepts
execution overshoot from gaps, slippage or exchange refusal. The earlier
guaranteed-final-maximum requirement is superseded, not a current blocker.
This reply is preparation authority; it is not exact monetary GO.

## Frozen preparation bounds

New policy `configs/research/kity_execution_micro_owner_bounds_v2_20261015.json`
SHA256 `49bf03e4733711d3c97c684ec2436fff988817e8fb6d9cef351b71708a882bb3`:

- gross≤210USDT; immediate all-in exit threshold15USDT;
- 30min from first durable entry intent, then owned close/readback;
- exact original5-long/5-short basket, each floor-rounding shortfall≤20.3%;
- one experiment, no averaging/scaling/re-entry;
- separate EXECUTION_MICRO_LIVE accounting, no KITY/C1–C3/edge inference;
- no orders until a separate exact human GO.

The original V1 policy, reports and receipts remain unchanged at commit
`687500d5443ee5145ee2a53d6d5c68d127d47873`. Its saved no-send preview replays
identically under the old policy, including the old guarantee blocker. New
default CLI preparation uses V2. The runtime/CLI continuation is pinned by the
new delivery receipt; old source hashes are historical, not claimed current.

## Implemented mechanism

The controller now persists `RISK_OBSERVATION` before returning an unwind
proposal. It values every proven owned quantity against full executable exit
depth at a common source-CTS clock≤2s, adds actual trade cash and signed funding,
subtracts known execution fees, estimated exit fees and a sourced remaining
funding reserve. Fill/exit prices already contain slippage: no duplicate debit.

At net≤−15, entry is permanently blocked and owned unwind is proposed. Price
recovery/restart cannot undo the recorded trigger. Missing/invalid/stale source,
fee or reserve produces UNKNOWN and a persistent unwind requirement, never0.
Malformed, nonfinite or oversized risk input also records a bounded UNKNOWN
event rather than leaving an unrecorded monitoring exception. Duplicate identical
observations are idempotent. The existing durable30min deadline remains unchanged.

Final accounting below−15 is reported as EXIT_THRESHOLD_OVERSHOOT, not as an
unbroken final-loss guarantee. V2 lifecycle receipts disclose each leg's rounding.
There is still no real sender, credential loader, service or activated monitor:
these are durable local decisions/action proposals, not proof of broker exits.

## Actual remaining blockers and next executable work

1. **Selected-account writer ownership/integration is not proven.** A bounded
   read-only VPS inventory completed by06:30:10UTC found the existing production
   PID1648585 with process environment `DRY_RUN=false`. Disk source initializes
   `TRADE_ON=True`; current in-memory TRADE_ON and loaded-code hash were not read.
   This is not a claim that a trade occurred. The earlier signed05:13 capture
   matched this PID's selected-account credentials. Earlier linear-USDT0/0 is
   dated broker truth and cannot prove exclusive ownership. A second independent
   sender must not be started alongside this process. Integrate through proven
   shared account ownership or prepare a separately reviewed scoped handoff;
   preserve existing ATT1/position management. No handoff/restart was performed.
2. **Physical transport/protection/recovery supervisor is not bound.** The local
   controller and normalized Bybit adapters do not establish authenticated GET
   custody, real dispatch/readback, native protection or continued owned recovery
   after host failure. Complete that integration with the writer arrangement;
   local synthetic PASS does not replace it. No additional research gate is added.
3. **Saved basket exceeds the210 cap and is expired.** The SAME05:13 source still
   gives210.266660 gross,0.266660 above210; LTC shortfall20.27157566% fits20.3%.
   No leg reduction/substitution, cap tolerance or extra capital is assumed.
   Only a later explicitly fresh executable basket can establish current sizing,
   account/depth/fees/funding feasibility. No new broker quote was requested here.
4. **Exact human money GO remains absent.** Produce a real executable dossier
   after the above integration/fresh checks, then obtain that GO. This policy
   clarification itself creates no permit/reservation or monetary authority.

Writer receipt: `evidence/kity_micro_policy_v2_20261015/writer_custody_receipt.json`.
Its private capture hash is `cddf46be4d26acdbfda8c4f2f383de2a98157e1084f78bdb59c09ba610155463`.
Exact remote observation milliseconds were not captured; local persistence time
and the actual completed-by bound are reported instead of an invented timestamp.

## Verification and preserved scope

**488 targeted tests PASS**: prior462 plus26 policy/monitor cases. Root review
reproduced two monitoring failures (malformed book envelope; oversized event),
then verified the narrow fixes. Exact−15 including fees/funding/reserve,
restart/price recovery, idempotence and preserved V1 replay are covered. Original
251 KITY signal vectors remain in the passing suite. Full repository suite was
not run. Independent review was not retried/replaced.

The old actual source/intake manifest is byte-identical and all its pins verify.
V1 saved preview is exactly unchanged under network denial; V2 preview and its
new plan are separately sealed. These are saved-source replays, not new market
observations, PAPER execution or LIVE readiness.

This cycle: one read-only SSH process/source inventory; zero broker requests,
zero broker/VPS writes, deployments, process changes or new automations. Private
capture remains0600. Alpaca Oct15 frozen preflight/HALT/owner-GO/opening, Claude's
checkout/processes, ATT1, liquidation and all research receipts remain untouched.
