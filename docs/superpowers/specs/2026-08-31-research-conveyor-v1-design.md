# Research Conveyor V1 Design

## 1. Purpose

Research Conveyor V1 turns the existing collection of research scripts into
one fail-closed, nightly, research-only queue. It does not invent results and
does not replace strategy-specific runners. It freezes inputs, invokes only
explicit adapters, validates their receipts, and publishes one terminal
receipt for every queued hypothesis.

The first queue contains ten families:

1. XSEC PIT V5;
2. Crypto Bull Continuation V1;
3. XAUUSD unchanged replication;
4. funding carry;
5. simple mean reversion;
6. breakout/retest;
7. cross-exchange arbitrage paper;
8. trend pullback;
9. session breakout;
10. range rejection.

The queue is a truthful readiness map. A family without exact data, a frozen
contract, or an adapter receives a terminal `BLOCKED_*` receipt. It is never
reported as tested merely because a process exited with code zero.

## 2. Authority boundary

V1 has exactly this authority:

`research_only_no_live_risk_order_promotion_or_private_api_authority`

It must not:

- import broker/order modules;
- read private API credentials;
- call a network service;
- change live config, risk, slots, positions, orders, or money authority;
- run `auto_apply_research_winner.py`;
- promote a discovery winner directly to shadow or money;
- read ATT1/SBR1 reserved OOS v1 again.

Ollama and paid models may submit proposal cards through the existing
`research_lab/idea_intake.py` contract. They cannot edit the executable queue,
approve a card, choose a terminal verdict, or launch a phase.

## 3. Architecture

V1 has four focused units:

1. `research_lab/research_conveyor_contract.py` validates the manifest,
   computes canonical hashes, validates phase receipts, and writes atomic
   self-hashed receipts.
2. `scripts/run_research_conveyor.py` owns the lock, resource guard, bounded
   subprocess execution, phase sequencing, and terminal aggregation.
3. `configs/research/research_conveyor_v1.json` is the sole executable queue
   and initial ten-family readiness registry.
4. `tests/test_research_conveyor_contract.py` and
   `tests/test_run_research_conveyor.py` prove strict schemas, fail-closed
   behavior, deterministic ordering, non-execution of blocked cards, and
   terminal receipt integrity.

Existing strategy runners remain independent. They join the conveyor only
through an adapter that emits the phase receipt protocol below.

## 4. Manifest contract

The top-level manifest is strict and contains:

- `schema_id = research_conveyor_manifest_v1`;
- `authority` equal to the exact authority string above;
- `enabled`;
- `max_jobs_per_run`, `max_runtime_seconds`, `min_free_bytes`;
- `allowed_script_roots` restricted to `research_lab/` and `scripts/`;
- one or more unique `hypotheses`; the repository's initial V1 manifest must
  contain exactly the ten approved families.

Each hypothesis contains only:

- stable `id`, `title`, `market`, `family`, and integer `priority`;
- `state`: `RUNNABLE`, `BLOCKED_ADAPTER`, `BLOCKED_DATA_OR_PARITY`, or
  `DISABLED`;
- `reopen_when` with a falsifiable condition;
- `contract_refs`: explicit project-relative files that are hashed before a
  run; globs and paths outside the repository are forbidden;
- `data_refs`: explicit required files/directories and an optional minimum
  count;
- exact `preregistration`: hypothesis, universe, signal, entry, exit, costs,
  control, stress, concentration, death criteria, and acceptance gate;
- for `RUNNABLE` only, four ordered phase adapters: `prereg`, `replay`,
  `random_control`, `stress`.

An adapter is an argv array, never a shell string. Its executable is the
current repository Python, and its script must resolve beneath an allowed
script root. The runner adds only declared placeholders for run directory,
hypothesis ID, phase, and output receipt. Unknown placeholders fail closed.

The initial queue may honestly contain no `RUNNABLE` card. That is still a
useful terminal readiness run: it proves which exact dependency blocks each
family. A card becomes runnable only in a scoped commit that adds its adapter,
tests, and frozen contract.

## 5. Phase receipt protocol

Every adapter writes one JSON object to the exact output path supplied by the
runner. The strict receipt contains:

- `schema_id = research_conveyor_phase_receipt_v1`;
- exact `authority`, `hypothesis_id`, and phase;
- `status`: `PASS`, `REJECT`, `INCONCLUSIVE`, `BLOCKED_DATA_OR_PARITY`, or
  `FAILED_TECHNICAL`;
- `manifest_sha256`, `preregistration_sha256`, and adapter argv hash;
- explicit input and output artifact hashes;
- metrics as a JSON object, permitted to be empty for a blocked result;
- `live_or_broker_calls = false`;
- `private_api_calls = false`;
- `capital_or_promotion_authority = false`;
- self-hash `receipt_sha256` over canonical JSON without that field.

Exit code is transport truth, not research truth. `rc=0` without a valid
receipt is `FAILED_TECHNICAL`. A valid negative receipt remains a successful
execution with a negative research verdict.

## 6. Run and terminal receipts

Each invocation creates a new run directory. Reusing a non-empty run
directory is forbidden. The runner writes:

- `manifest_snapshot.json` and its hash;
- one normalized preregistration per selected hypothesis;
- phase receipts and bounded stdout/stderr logs;
- one terminal receipt per hypothesis;
- one aggregate `terminal_receipt.json`.

Terminal hypothesis states are:

- `PASS_DIAGNOSTIC` only when all four phases pass;
- `REJECT` when any valid research phase rejects;
- `INCONCLUSIVE` when a valid phase is inconclusive;
- the declared `BLOCKED_*` state when the card is not runnable;
- `RESOURCE_GUARD` when disk/time/process budget prevents execution;
- `FAILED_TECHNICAL` for schema, hash, adapter, timeout, or process failures.

The aggregate receipt records every family, including disabled and blocked
ones, plus counts by state. It never contains a promotion recommendation.

## 7. Scheduling and resource safety

The runner is deterministic: priority ascending, then hypothesis ID. One
process runs at a time in V1. It uses an exclusive lock and never silently
reclaims a live lock. Before every phase it verifies:

- repository root and manifest hash are unchanged;
- all contract hashes are unchanged;
- available disk is at least `min_free_bytes`;
- wall-clock budget remains;
- no adapter path escapes its allowlist;
- the sanitized environment contains no variable whose name includes
  `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `CREDENTIAL`, or `PRIVATE`.

V1 has `--dry-run`, `--preflight`, and `--run`. Dry-run never launches an
adapter. Preflight writes terminal readiness receipts but never launches an
adapter. Run launches only `RUNNABLE` cards and still emits receipts for all
blocked cards.

No scheduler is installed or enabled merely by merging V1. The first manual
run and its independent audit must pass before a local nightly LaunchAgent or
cron entry is proposed.

## 8. Initial queue truth

The ten cards begin from current evidence, not optimism:

- XSEC PIT V5 is `BLOCKED_DATA_OR_PARITY` until causal histories for delisted
  contracts exist; current-137 substitution is forbidden.
- Bull Continuation is `BLOCKED_ADAPTER` until its detector, execution model,
  controls, and frozen runner exist.
- XAU replication is `BLOCKED_DATA_OR_PARITY` until an independent causal
  source and cost/parity preflight exist.
- funding, mean reversion, breakout/retest, trend pullback, session breakout,
  and range rejection have legacy components but remain `BLOCKED_ADAPTER`
  until their output is converted to the strict four-phase protocol.
- cross-exchange arbitrage paper is `BLOCKED_DATA_OR_PARITY` until synchronized
  venue data and an execution-cost adapter exist.

This baseline is intentionally honest. The next conveyor commits convert one
family at a time to `RUNNABLE`, beginning with the shared control dependency
used by XSEC, Bull, and XAU.

## 9. Acceptance tests

V1 is complete when:

1. malformed/unknown manifest fields, duplicate IDs, globs, path escape,
   missing contract refs, and runnable cards without four phases fail closed;
2. blocked cards never launch a subprocess and still receive terminal
   receipts;
3. dry-run and preflight launch zero subprocesses;
4. a synthetic four-phase adapter can reach `PASS_DIAGNOSTIC` only with four
   valid self-hashed receipts;
5. invalid hash, missing receipt, nonzero exit, timeout, secret-like env, disk
   guard, or changed manifest produces a non-promotional failure state;
6. repeated manifests produce stable preregistration hashes and deterministic
   order;
7. the initial manual preflight emits ten terminal hypothesis receipts and an
   independently verifiable aggregate receipt;
8. all focused tests, `py_compile`, `git diff --check`, secret scan, scoped
   commit, and push pass.
