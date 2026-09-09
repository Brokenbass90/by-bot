# ATT1 profile migration and activation plan

> For agentic workers: execute bounded tasks with superpowers:executing-plans.
> This is a preparation plan. Do not execute financial activation or rewrite
> the existing public epoch. Money routing changes are owner-operated.

**Goal:** prepare one exclusive NEW ATT1 coordinator path at no greater absolute
risk than OLD, with zero-risk comparison retained and no duplicate money signal.

**Architecture:** reuse the existing bybot process, entry reservation, broker
transport, durable lifecycle and L2/L3 reducer. Replace the ATT1 entry/management
route at a verified flat handoff; do not introduce a second independently
credentialed ATT1 trading service or a new strategy/core.

**Tech Stack:** existing Python, Bybit linear-USDT transport, exact integer-step
exposure/Fraction accounting, source-bound journal, systemd packaging.

**Spec:** `reports/ATT1_MICRO_CANARY_RECONCILIATION_2026_09_08.md` and the owner's
September 8 OLD/NEW reconciliation and no-increase/max-1 requirements.

## Fixed migration decisions

- Canonical next strategy is NEW, profile reference
  `79d23e38a6bb851fb7e300c2e0d0c22b48b671585d4c060eb5384c192b128050`.
  Preserve its signal, original stop, target rebasing, BE/trailing OFF, 336h exit.
- Existing synthetic profile and its risk=1/notional=100 are immutable evidence.
  A separately hashed money execution binding must identify the changed risk,
  quantity, transport and actual-cost provenance; no false byte-for-byte claim.
- Draft absolute initial-stop cap: **OWNER_STOP_RISK_USDT**, additionally bounded by a
  fresh fully known OLD budget. No equity growth increases this pinned cap.
- Initial money admission universe: OLD's eight symbols, all present in NEW.
  NEW signal generation stays frozen Fixed51; this is a capital-admission gate.
- Max one account-wide ATT1 reservation/position across pending, partial,
  unknown-order, recovery and protected/exit states. Unknown counts as occupied.
- Notional ceiling at most **100 USDT**, additionally bounded by broker margin,
  instrument limits and fixed stop-risk cap. Floor quantity; reject below venue
  minimums. No min-quantity fallback. Price/stop rounding cannot raise absolute R.
- Draft daily loss admission budget **OWNER_DAILY_LOSS_USDT = 2×OWNER_STOP_RISK_USDT**, UTC day boundary.
  Include all OLD+NEW ATT1 net debits for that day, fees and funding, plus open/
  pending risk and cost reservations. Do not reset on restart, route switch,
  profitable trade or administrative retry. Unknown costs block new admission.
  This limits admission; market gaps cannot be promised an absolute loss bound.
- All numbers above are inert design values. Existing OLD risk/settings stay
  unchanged while preparation runs. Zero-risk v1 remains public-only in parallel.

## Task 1 — Close the observed public continuity blocker

Files: existing `scripts/run_att1_lifecycle_zero_risk.py`, its tests and current
standalone fixture. Preserve the captured public journal and existing v1 epoch.

- [x] Capture the real ADA gap journal, verify chain, repeat replay and retain
  flat exposure, scenario costs and null clean net-R identically.
- [x] Add targeted fixtures for >2s optional scan and slow book response. The
  retained historical journal cannot identify the exact slow phase; do not infer
  historical attribution from a synthetic reproduction or repeat a broad audit.
- [x] Give open-position observation priority within the existing driver; retain
  fail-closed incident semantics and the 2s limit. No new strategy/scheduler core.
- [x] Prove fixture cycles remain within the bound and genuinely delayed cycles
  stay dirty. Stop repeated flat, fully-covered funding polling without clearing
  incidents or pretending dirty lifecycle finality is clean evidence.
- [x] Verify in target Python and a distinct public epoch/release if deployment
  is needed. Never mutate source binding under existing durable v1 journals.

## Task 2 — Bind real evidence to the existing coordinator, send disabled

Files: existing `research_lab/att1_lifecycle_profile.py`, coordinator/session and
L3 accounting contract; thin proposed `bot/att1_coordinator_adapter.py`; existing
`smart_pump_reversal_bot.py` ATT1 entry/runner integration. No duplicate core.

- [x] Extract only the minimal execution/provenance binding needed to reuse
  frozen strategy admission at the lower risk. Existing SYNTHETIC profile bytes,
  authority and expected receipts must remain valid and unchanged.
- [ ] Adapter inputs are immutable signal/instrument/book admission inputs plus
  broker ACK/fill/finality/protection and signed cost evidence. Outputs are
  existing coordinator events and requested intents; no independent SL/TP logic.
- [ ] Map actual `orderId/orderLinkId/execId`, exchange timestamps and receive
  timestamps. ACK is not fill; timeout is not nonfill; cancel request is not
  finality. Re-delivery must preserve stable execution identity and exact fees.
- [ ] For every entry/partial fill, read and prove actual protective quantity and
  stop from broker evidence. Never manufacture PROTECTION_ACK from an HTTP ACK.
  Any unproven protection blocks new entry and enters the existing incident path.
- [ ] Map exits to coordinator decisions, reduce-only broker operations and exact
  final remainder. Freeze initial R0 once final entry quantity is known; target
  rebasing and first-fill time deadline must match the NEW coordinator.
- [x] Support signed funding cash debits/credits and explicit coverage. Previous
  L3 funding accepts quantity×mark×rate, not a broker cash amount: extend evidence
  binding minimally and test broker rounding; never invent a synthetic mark/rate
  to force agreement. Retain fees/funding provenance separately from scenarios.
- [ ] Bind account identity, account mode, fresh balances, fee tier, source/profile
  hashes, risk cap and journal identity before any possible send. Missing/changed
  values fail closed. No fallback to the OLD entry path on NEW error.

## Task 3 — Exclusive handoff and no-duplicate fixtures

Use the current ATT1 entry dispatch/reservation and the coordinator journal;
do not add another trading daemon. Required persisted facts are route owner,
activation epoch/H1 watermark, consumed decision keys and cooldown timestamps.

```text
Current: OLD_ENTRY + OLD_MANAGEMENT; NEW_SEND_DISABLED; public v1 runs
Preparation: same money state; all adapter fixtures/receipts are inert
Owner handoff: OLD_NEW_ENTRIES_PAUSED; OLD_MANAGEMENT continues until drained
Preactivation: broker flat + no orders + all old intents final/reconciled
Eligible: NEW sole ATT1 entry/management route, only H1 closes >= cutover C
Incident: no new entries; keep protection/reconciliation/exit management alive
```

- [ ] Prove the persisted OLD pause survives process restart and every loader,
  operator override and watchdog. `bybot.service` itself stays operational.
- [ ] After pause, drain OLD naturally; do not adopt or reprofile an existing OLD
  position. A late fill returns the handoff to draining; unknown finality blocks.
- [ ] Choose C as a fresh H1 close strictly after confirmed drain and the latest
  OLD evaluated/admitted signal. Carry forward each symbol's 8h cooldown and
  terminal watermark. Do not replay pre-C signals for NEW.
- [ ] Dedupe key is `(account, ATT1 family, symbol, side, H1 close)` independent of
  OLD/NEW profile hash. Commit consumption/reservation durably before send.
  Deterministic client order identity and broker lookup resolve send timeout;
  never resend with a fresh identity while acknowledgement is uncertain.
- [ ] One global ATT1 reservation blocks a second symbol as well as a duplicate
  signal. Partial fill, pending cancellation or unknown position owns the slot.
- [ ] Run fixtures: same signal in OLD+NEW, concurrent symbols, crash before send,
  crash after possible send before ACK, delayed fill after pause, duplicate fill,
  restart with unknown order, missing SL, partial TP1/final dust, delayed funding,
  fee mismatch, risk rounding above cap, insufficient lot size and UTC rollover.
- [ ] Assert for every fixture: no simultaneous OLD/NEW send, no more than one
  slot, no risk increase, exact costs/net-R or explicit null on incomplete cost,
  restart reproduces state and consumed decision IDs without a second order.

The no-duplicate guarantee is conditional on these implemented checks. Present
state has no NEW order capability; a future separate NEW service on the same
account alongside an unpaused OLD is explicitly disallowed by this plan.

## Task 4 — Owner activation dossier and first 1–3 real lifecycles

- [ ] Require clean prospective evidence after fixing the observed gap, broker
  binding/fixtures PASS, fully bound current absolute-risk inputs, fresh direct
  flat/finality/protection/cost truth and source parity on target Python.
- [ ] Package exact source commit/file hashes and default-disabled money binding;
  zero-risk retains its independent service, profile/epoch and scenario costs.
- [ ] Emit `READY FOR OWNER ACTIVATION` only when every prerequisite above has a
  linked PASS receipt. Current report/verification deliberately emits false.
- [ ] Owner performs the reviewed financial route transition. Record a receipt
  only from observed activation state, never from proposed config:
  `LIVE MICRO-CANARY ENABLED / bound risk / max 1 + notional / kill conditions /
  account fingerprint / service source commit + binding hash + cutover C`.
- [ ] For each of the first 1–3 NEW completed lifecycles join signal/source hashes,
  expected public fill, actual broker fills, actual protection, exit intent/fills,
  fees, signed funding, fixed R0 and net-R. Preserve OLD historical comparisons
  separately; compare shadow per-unit/R-normalized values because quantities,
  virtual risk and fee sources differ. Missing shadow signal is reported missing.
- [ ] On incident, recovery mismatch, missing protection, duplicate owner, risk
  overrun or incomplete/conflicting costs, close admission. Preserve journals and
  active management; never auto-resume OLD or clear dirty evidence to continue.

September 9 cycle: public continuity fix deployed in a distinct v2 service;
167 tests and target-Python/23-prefix recovery proofs PASS. Existing v1, OLD and
L1 preserved. Transport-free broker-shaped record mapping, separate profile and
exact cash funding replay implemented. See
`reports/ATT1_PUBLIC_V2_AND_BROKER_REPLAY_2026_09_09.md` for exact receipts.
Production account authentication, exclusive dispatch/handoff, durable global
slot/daily budget and a clean prospective v2 cohort are still open. A pure replay
binding is not installed financial authority and does not prove those gates.

Public export: monetary values and account evidence are owner-private inputs.
The original full plan remains in the local private-evidence branch.
