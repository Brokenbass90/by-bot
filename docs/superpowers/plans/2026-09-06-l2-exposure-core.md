# L2 synthetic exposure core implementation plan

> For agentic workers: use superpowers:subagent-driven-development. This is one
> bounded slice of the reviewed L2/L3 design, not the full L2 parity gate.

**Goal:** Replay exact partial-entry/protective-exit exposure and cancellation
finality without hidden dust, duplicate executions or broker capabilities.

**Architecture:** Pure immutable reducer over explicitly synthetic event records.
One reducer instance owns one virtual short position and entry order. No market
adapter, profile inference, cash accounting, persistence writer or live imports.
**Tech stack:** Python stdlib dataclasses, Decimal, hashlib/json; pytest.
**Spec:** `docs/superpowers/specs/2026-09-06-att1-ets2s-l2-l3-contract.md`.

## Global constraints

- All authority flags false. No network, broker, subprocess or filesystem calls
  in the module. Production L1 files and source closure stay unchanged.
- This slice is SYNTHETIC_EXPOSURE_CORE only. ATT1 full geometry, ETS2S profile,
  price-triggered SL/TP/BE/trail, L3 cash and persisted restart remain next gates.
- Use integer quantity steps internally. Parse only finite positive decimal
  strings for quantity step and requested/fill quantities, rejecting floats,
  bools, NaN/infinity, non-step multiples and quantities <=0.
- Event IDs identify identical canonical payloads; exact replay is a no-op,
  conflicting reuse raises a violation. Execution IDs additionally deduplicate
  fills, even when event IDs differ; conflicting execution payload fails.
- No synthetic expected values may be calculated using reducer functions.

### Task 1: Pure exposure reducer and independent tests

Files: create `research_lab/att1_ets2s_lifecycle.py` and
`tests/test_att1_ets2s_lifecycle.py`; no other implementation files.

API: frozen `ExposurePlan` (book/sleeve/symbol/decision_id/order_id,
qty_step/requested_qty, submit_ms; explicit profile_id prefixed SYNTHETIC_).
Frozen `ExposureEvent` (event_id, kind, order_id, exchange_ms, received_ms,
optional execution_id and qty). Frozen `ExposureState`; `initial_state(plan)`,
`apply_event(state,event)`, `replay(plan,events)` and
`target_close_qty(initial_qty,remaining_qty,qty_step,fraction,final=False)`.
Expose exact held/pending entry/protected quantities and terminal eligibility.
State owns immutable maps/tuples of accepted event and execution fingerprints.

Event semantics decided by orchestrator:

- ENTRY_ACK is idempotent acknowledgement only; no held exposure.
- ENTRY_FILL adds actual held qty and consumes pending entry qty. Partial
  exposure produces protection intent; protection remains separate and unknown
  until PROTECTION_ACK. Do not discard a fill because protection is unknown.
- CANCEL_REQUEST sets a request flag only; outstanding quantity stays pending.
- ENTRY_FINAL makes remaining unfilled qty zero, proving no more expected
  entry fills (reject/expire/cancel/IOC completion share this synthetic event).
- EXIT_FILL reduces held qty even before entry finality and even while
  protection is unknown. Requires a unique execution ID; qty cannot exceed held.
  Protection coverage is clamped to remaining held qty after a reduction.
- PROTECTION_ACK sets confirmed protected qty to explicit qty <= held; any
  positive difference is visible as unprotected. UNKNOWN_PROTECTION clears
  confirmation; it does not erase held qty or block emergency exits.
- ENTRY_FILL after finality or above planned remaining qty must still expose
  observed quantity and mark sticky INCIDENT_UNEXPECTED_ENTRY_FILL. It cannot
  produce a clean terminal result. This is observation accounting, not permission
  to place such an order. Foreign order ID raises a violation.
- All events require nonnegative integer timestamps (bool rejected),
  submit<=exchange<=received, and nondecreasing receive times. Reject decreasing
  exchange times as unresolved late ordering; never sort input retrospectively.
- Terminal eligible iff entry final, held==0, and no sticky incident. Flat held
  with pending entry is never terminal. No admission of another decision in this
  slice; per-position replay itself has no DCA command.
- Intermediate target quantity floors original qty*fraction to step, capped by
  remaining qty; final target returns exact remaining qty. Zero planned target
  is allowed. Fraction is a finite decimal string in (0,1]. Final still validates
  all inputs. Remaining cannot exceed initial for this clean planning helper.

Tests first (RED), then minimal implementation (GREEN), then self-review:

1. ACK/partial .1 of .3: held .1, pending .2, protected 0; not terminal.
2. Partial fill -> protect -> exit while entry pending -> late fill -> cancel
   final -> emergency exit: quantity conserved; zero before final is not terminal.
3. Cancel request alone permits late fill; final cancellation ends only pending.
4. Late fill after finality and overfill stay visible and incident-sticky.
5. Duplicate identical event/execution causes no extra quantity; conflicts fail.
6. Exit overfill and foreign-order fill reject; input state remains unchanged.
7. .3 at step .1 and fraction .55 => .1 then final .2 then zero held, no dust.
8. Unknown protection and partial coverage remain explicit; exit still works.
9. Invalid decimals, step multiples, profile IDs and causal timestamps fail.
10. Replaying same ordered fixture returns equal immutable state; earlier state
    cannot be mutated through exposed collection references.

Use `.venv/bin/python -m pytest -q tests/test_att1_ets2s_lifecycle.py`.
Report exact RED/GREEN commands and counts; no commits by worker. Parent reviews
event identity, quantity conservation and fail-closed claims, then records scope.

### Task 2: Integration evidence and continuity

Parent runs scoped L1 + burn-in + lifecycle tests, verifies original deployed
source closure unchanged, records runtime model/effort evidence, and updates
checkpoint/roadmap with the precise next L2/L3 gap. Commit only scoped changes.
