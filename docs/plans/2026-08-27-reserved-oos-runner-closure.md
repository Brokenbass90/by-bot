# RESERVED_OOS_RUNNER_CLOSURE implementation plan

**Goal:** make the known-contaminated ATT1/SBR1 reserved diagnostic ready for
one separately authorized execution without scoring the reserved window during
this plan.

## Global constraints

- Reserved window is exactly `[2025-10-01T00:00:00Z, 2026-07-01T00:00:00Z)`.
- Universe is the frozen major-8 order in
  `configs/research/att1_sbr1_live_native_parity_v1.json`.
- Data materialization may use public Bybit market endpoints only. No private
  API, broker, order, risk, live-config, selector, geometry, cost, threshold or
  money-authority mutation.
- Materialization may decode rows only to validate and freeze their identity;
  it must compute no signals, trades, returns or performance.
- The one-shot runner must create a durable atomic claim before the first
  reserved market-file open and must refuse every retry, including after a
  failed or interrupted attempt.
- Runner and independent audit must be exact SHA-pinned by the preflight.
- This plan stops at `READY_FOR_OWNER_AUTHORIZATION`; execution of the one-shot
  requires a later explicit owner authorization artifact.

## Task 1: exact no-score M5 identity materializer

Create `scripts/materialize_att1_sbr1_reserved_m5_v1.py` and focused tests.

- Require an explicit public-network acknowledgement.
- Fetch only the frozen major-8, exact window, exact M5 interval.
- Validate ordered unique contiguous rows, exact first/last timestamps, exact
  expected row count, OHLC sanity and no conflicting duplicate.
- Write each payload atomically under ignored
  `data_cache/immutable/att1_sbr1_reserved_m5_v1/`.
- Support verified reuse of completed payloads so a network interruption does
  not require refetching good files.
- Atomically write
  `configs/research/att1_sbr1_reserved_m5_input_manifest_v1.json` with paths,
  bytes, SHA-256, rows, first/last timestamps, materializer SHA and explicit
  `performance_computed=false`, `money_authority=false`.

Verification: unit tests for exact window/universe, gap/duplicate rejection,
atomic/reuse behavior and manifest schema; then materialize all eight inputs
without running a strategy.

## Task 2: frozen one-shot runner

Create `scripts/run_att1_sbr1_reserved_oos_v1.py` and focused tests.

- Validate an owner authorization file that pins config, manifest, runner,
  audit, output and claim identities.
- Refuse before data access when authorization is absent/invalid.
- Create the fixed claim with `O_CREAT|O_EXCL`, fsync it and its directory, then
  record market-decode start. A pre-existing claim always refuses execution.
- Verify every reserved input hash/size/schema/window before decoding rows.
- Reuse the frozen live-native strategy/wrapper/fill/outcome boundary without
  changing its source or parameters.
- Produce byte-parity ledgers, base/stress economics, per-sleeve three-way
  decision (`PASS_ZERO_RISK_INTEGRATION_ONLY`, `FAIL_CLOSED`,
  `INCONCLUSIVE_LOW_N`) and immutable output hashes.
- Every outcome remains research/zero-risk only; no automatic promotion.

Verification: negative tests prove no authorization/no data open, claim-before-
callback, retry refusal, hash drift refusal and fail-closed decision rules.

## Task 3: independent audit and preflight freeze

Create `scripts/audit_att1_sbr1_reserved_oos_v1.py` and focused tests.

- Before execution, validate the frozen config/manifest/runner/audit identities
  and absence of claim/result; never open market inputs.
- After execution, independently verify claim timing, authorization hash,
  research/live ledger parity, ledger hashes, metrics and decision derivation.
- Update the diagnostic config with manifest, runner and audit SHA pins and
  recompute its canonical fingerprint.
- Rerun metadata-only preflight. Expected result is
  `READY_FOR_OWNER_AUTHORIZATION`, zero market files/rows opened by preflight,
  zero performance computed and zero money authority.

## Task 4: verification and handoff

- Run focused tests, compile checks, source/secret scan and Git scope review.
- Update the canonical checkpoint with current live/shadow/Alpaca facts and the
  exact one-shot authorization gate.
- Commit and push only the reviewed closure package. Do not create the owner
  authorization file and do not execute the runner.
