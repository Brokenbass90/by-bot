# Research Conveyor V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fail-closed research-only queue that records a truthful terminal receipt for ten strategy families and runs only explicitly adapted four-phase experiments.

**Architecture:** A strict contract module owns validation and hashing; a separate CLI owns bounded sequencing and subprocesses; one JSON manifest is the executable queue. Existing research programs remain independent and must emit the conveyor phase-receipt protocol through scoped adapters.

**Tech Stack:** Python 3.11 standard library, JSON, hashlib, pathlib, subprocess, pytest.

**Spec:** `docs/superpowers/specs/2026-08-31-research-conveyor-v1-design.md`

## Global Constraints

- Authority is exactly `research_only_no_live_risk_order_promotion_or_private_api_authority`.
- No broker, order, live config, private API, risk, slot, or promotion changes.
- No shell command strings, network calls, `auto_apply_research_winner.py`, or consumed ATT1/SBR1 OOS reuse.
- Unknown fields, missing hashes, path escape, stale/changed inputs, and missing receipts fail closed.
- Initial blocked candidates must still publish terminal receipts and must never be called tested.

---

### Task 1: Strict manifest and receipt contract

**Files:**
- Create: `research_lab/research_conveyor_contract.py`
- Test: `tests/test_research_conveyor_contract.py`

**Interfaces:**
- Produces: `load_manifest(root: Path, path: Path) -> ConveyorManifest`
- Produces: `freeze_hypothesis(root: Path, manifest: ConveyorManifest, hypothesis_id: str) -> dict[str, Any]`
- Produces: `write_self_hashed_json(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]`
- Produces: `read_verified_receipt(path: Path, *, expected_schema: str) -> dict[str, Any]`

- [ ] **Step 1: Write failing strict-schema and hashing tests**

  Cover unknown fields, duplicate IDs, path escape, globs, missing refs,
  incomplete `RUNNABLE` phases, deterministic preregistration hash, atomic
  self-hash verification, and tampering.

- [ ] **Step 2: Run the focused tests and verify failure**

  Run: `pytest -q tests/test_research_conveyor_contract.py`

  Expected: import failure because the contract module does not exist.

- [ ] **Step 3: Implement typed immutable manifest objects and canonical JSON**

  Use dataclasses frozen at construction, explicit allowlists for every object,
  `json.dumps(..., sort_keys=True, separators=(",", ":"), allow_nan=False)`,
  and SHA-256. Resolve every path beneath the repository root.

- [ ] **Step 4: Run focused tests**

  Run: `pytest -q tests/test_research_conveyor_contract.py`

  Expected: PASS.

- [ ] **Step 5: Commit Task 1**

  ```bash
  git add research_lab/research_conveyor_contract.py tests/test_research_conveyor_contract.py
  git commit -m "feat: define research conveyor contract"
  ```

### Task 2: Bounded runner and terminal aggregation

**Files:**
- Create: `scripts/run_research_conveyor.py`
- Create: `tests/fixtures/research_conveyor_phase_adapter.py`
- Test: `tests/test_run_research_conveyor.py`

**Interfaces:**
- Consumes: Task 1 manifest, preregistration, and receipt functions.
- Produces: `run_conveyor(root: Path, config_path: Path, run_dir: Path, mode: str, now: datetime | None = None) -> dict[str, Any]`
- Produces CLI modes `--dry-run`, `--preflight`, and `--run`.

- [ ] **Step 1: Write failing runner tests**

  Verify deterministic order, exclusive new run directory, blocked-card
  non-execution, four valid synthetic phases, missing/tampered receipt,
  timeout, nonzero exit, resource guard, sanitized environment, and aggregate
  state counts.

- [ ] **Step 2: Run focused tests and verify failure**

  Run: `pytest -q tests/test_run_research_conveyor.py`

  Expected: import failure because the runner does not exist.

- [ ] **Step 3: Implement the minimal runner**

  Use `subprocess.run(argv, shell=False, cwd=root, timeout=remaining_budget)`,
  one phase at a time, a stripped environment, bounded log capture, and one
  exclusive lock. Validate the phase receipt after every process and stop the
  hypothesis at the first non-PASS research state or technical failure.

- [ ] **Step 4: Run focused tests**

  Run: `pytest -q tests/test_run_research_conveyor.py`

  Expected: PASS.

- [ ] **Step 5: Commit Task 2**

  ```bash
  git add scripts/run_research_conveyor.py tests/fixtures/research_conveyor_phase_adapter.py tests/test_run_research_conveyor.py
  git commit -m "feat: run bounded research conveyor"
  ```

### Task 3: Initial ten-family queue and truthful preflight

**Files:**
- Create: `configs/research/research_conveyor_v1.json`
- Modify: `tests/test_run_research_conveyor.py`

**Interfaces:**
- Consumes: Task 2 CLI and strict Task 1 manifest schema.
- Produces: exactly ten stable hypothesis cards with explicit blocker and
  reopen condition.

- [ ] **Step 1: Add a failing repository-manifest test**

  Assert exact ten IDs, unique priority ordering, resolvable contract refs,
  no `RUNNABLE` card without four phases, no live/private authority, and
  expected initial blocker for XSEC/Bull/XAU/arbitrage.

- [ ] **Step 2: Run the test and verify failure**

  Run: `pytest -q tests/test_run_research_conveyor.py -k repository_manifest`

  Expected: missing manifest.

- [ ] **Step 3: Write the ten-family manifest**

  Bind each card to its current plan, prereg, strategy, or autoresearch config.
  Mark legacy-only families `BLOCKED_ADAPTER`; mark missing causal data
  `BLOCKED_DATA_OR_PARITY`. Give every card exact death criteria and a
  falsifiable `reopen_when`.

- [ ] **Step 4: Run the initial preflight**

  Run:
  `python3 scripts/run_research_conveyor.py --config configs/research/research_conveyor_v1.json --run-dir runtime/research_conveyor/manual_20260831_v1 --preflight`

  Expected: ten hypothesis receipts, zero adapters launched, aggregate
  authority research-only, terminal result with explicit blocker counts.

- [ ] **Step 5: Verify the receipt independently in tests**

  Run: `pytest -q tests/test_research_conveyor_contract.py tests/test_run_research_conveyor.py`

  Expected: PASS.

- [ ] **Step 6: Commit Task 3**

  ```bash
  git add configs/research/research_conveyor_v1.json tests/test_run_research_conveyor.py
  git commit -m "feat: seed research conveyor queue"
  ```

### Task 4: Operator handoff, full verification, and push

**Files:**
- Modify: `research_lab/RESEARCH_STATION_V3.md`
- Modify: `reports/CURRENT_HANDOFF.md`
- Modify: `reports/current_project_state.json`

**Interfaces:**
- Consumes: initial preflight terminal receipt and all Task 1-3 tests.
- Produces: exact manual commands and the first adapter-conversion queue.

- [ ] **Step 1: Document authority, commands, verdict semantics, and rollback**

  State that `PASS_DIAGNOSTIC` is not promotion, `BLOCKED_*` is a valid
  terminal result, and no scheduler is installed yet. List the first three
  adapter tasks: shared XSEC controls, Bull detector/execution, then XAU data
  parity.

- [ ] **Step 2: Run complete verification**

  Run:

  ```bash
  pytest -q tests/test_research_conveyor_contract.py tests/test_run_research_conveyor.py tests/test_experiment_lifecycle.py tests/test_market_scanner_idea_intake.py
  python3 -m py_compile research_lab/research_conveyor_contract.py scripts/run_research_conveyor.py
  git diff --check
  ```

  Expected: all tests and compile checks PASS.

- [ ] **Step 3: Run secret and scope checks**

  Confirm only the planned files are staged and no credential-shaped values,
  runtime artifacts, logs, `.env`, snapshots, or backups are included.

- [ ] **Step 4: Commit documentation**

  ```bash
  git add research_lab/RESEARCH_STATION_V3.md reports/CURRENT_HANDOFF.md reports/current_project_state.json
  git commit -m "docs: hand off research conveyor v1"
  ```

- [ ] **Step 5: Push and reconcile upstream**

  Run: `git push origin codex/recovery-20260824`

  Expected: local HEAD equals `origin/codex/recovery-20260824`.
