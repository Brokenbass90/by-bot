# PUMP4 V1: callable reference-plan adapter

**REFERENCE PLAN COMPONENT PASS; broker executor and TINY are NOT READY.**
Frozen contract b1387354e5b64de205e7f933b0537a2f6f37c123; corrected request
7b0a961863cdb2749f247f95d17535656ac582c3. This extends the accepted producer replay
with a callable implementation; it does not repeat an economic evaluation.

`research_lab/pump4_execution_plan_v1.py::build_plan` accepts a frozen signal and
the next hourly open, validates geometry and returns a deterministic plan/hash:
static stop x4, TP1 40%, remaining 60% at TP2, hold168H1, stop-first semantics,
model6bps/side. Signal trail/BE/time_stop48/tp3 do not enter V1. PF_* environment
or changed frozen producer bytes reject. Geometric leverage ceiling100 preserves
the research rule; it is NOT permission to use that exchange leverage.

## Verification

- 12 focused cases PASS; initial missing-component RED recorded before implementation.
- Actual frozen producer -> callable plan:65unique fixture matches;1ASTER source
  unavailable. Exact fixture/bar/source hashes checked, network disabled, research
  inputs unchanged. No R/outcomes/judge/funding evaluation and no broker requests.
- One bounded astra/high independent review:12overlapping tests PASS, no actionable
  findings. Reviewer inspected verifier and validated existing receipt hashes/counts;
  root executed the65-case producer/adapter parity. No second independent parity run.

[Parity receipt](evidence/pump4_execution_plan_20261021/parity.json),
[reproduction](evidence/pump4_execution_plan_20261021/verify.py),
[test receipt](evidence/pump4_execution_plan_20261021/tests.xml).

## Next exact gate

Durable, causal hourly intake/cursor and cooldown continuity: one closed-bar call,
restart without duplicate signal, changed duplicate/missing bar rejected. Start
with ZRO/BLESS cooldown cases from the frozen contract. Then bind existing Bybit
transport/native protection/reconciliation to entries and40/60partial exits;
prove lost replies/restarts/funding/actual fees/instrument minima and bounded TINY.

This component does not validate the137instrument universe, prove an actual next
open fill, size a quantity, round instrument prices, place native orders or run a
stop-first simulator. Those facts remain explicit NOT_PERFORMED. Funding UNKNOWN,
continuous-state/restart parity NOT_RUN. No LIVE/TINY GO or financial scope issued.

28Oct remains an executor acceptance/BLOCKED checkpoint, not a promised first trade
or return. KITY remains separate SPENT/ORDERS_OFF; no policy reuse or new launch.
