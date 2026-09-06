# LAB_AI_V0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, read-only, secret-free evidence assistant whose deterministic context pack and bounded Ollama proposals are reproducible, cited, hash-bound, and unable to mutate research or money authority.

**Architecture:** V0A first creates a strict allowlisted context pack from existing reports, ledgers, and receipts, records freshness/redaction/hash outcomes, and emits immutable input/output receipts. Tasks 1–3 are the first executable vertical slice; the deterministic pack can be tried before the convenience runner or V0B–V0D follow-ons. V0B adds a disposable DuckDB exact/lexical index, V0C adds typed read-only laboratory tools, and V0D gates the system with a frozen adversarial evaluation set before any quiet schedule. Source files and existing hash-bound ledgers remain truth; every derived index and model response is disposable proposal data.

**Tech Stack:** Python standard library, strict JSON/JSONL, `pathlib`, `hashlib`, atomic write-once receipts, `pytest`, local Ollama `qwen3:8b`; DuckDB is introduced only in V0B; Qdrant is conditional on measured retrieval improvement; MLX-LM QLoRA is V1 only.

**Spec:** `docs/superpowers/specs/2026-09-06-lab-ai-v0-design.md`

## Global Constraints

- Authority is exactly `local_readonly_secret_free_proposal_only_no_code_config_process_network_broker_order_risk_promotion_deploy_or_money_authority`.
- The model may retrieve allowlisted non-secret evidence, compare deterministic receipts, group materialized failures, identify stale or contradictory claims, and propose bounded falsifiable experiments.
- The model may not read `.env`, credentials, private broker payloads, unrestricted logs, or the whole filesystem; execute shell commands; write code/config/runtime/registry/deployment files; change a trial, verdict, strategy, parameter, risk, or authority; call a broker or public/private network API; or declare profitability or promotion.
- Ollama access is limited to a loopback endpoint (`127.0.0.1` or `localhost`); the call is bounded, one-shot, and proposal-only. A non-loopback URL fails closed.
- Unknown fields, duplicate JSON keys, non-finite numbers, invalid JSON, path escape, glob paths, symlink escapes, stale required inputs, size overflow, and unverifiable hashes fail closed.
- Every input and output receipt is canonical JSON with a SHA-256 self-hash, written to a new run-specific path with overwrite refusal. A later run creates a new receipt; it never replaces an earlier receipt.
- Source path, source SHA-256, observed timestamp, schema/type, freshness state, and redaction summary are retained for every collected source. Missing, stale, superseded, and contradictory evidence is surfaced explicitly as `NOT_CONFIRMED`.
- Numeric factual claims require a resolvable source path and SHA-256 citation. Model text never becomes numeric truth.
- DuckDB, Qdrant, Polars, DVC, MLflow, Optuna, and adapters are derived or later-stage capabilities; none becomes a source of truth or an automatic promotion path.
- Safe local analysis, scripts, and research experiments are authorized within these boundaries, including an independent Market Perception forecasting baseline track; no such experiment may consume sealed evidence or change money, risk, or current-position authority.
- The deployed ATT1/ETS2S shadow remains unchanged through its 72-hour burn-in and the P0 L2/L3 lifecycle gates. LAB_AI_V0 runs locally in bounded resource budgets and must not delay market-data collectors, VPS shadows, burn-in evaluation, or execution-parity work.
- No VPS access, network calls beyond the explicitly allowed local Ollama loopback, secrets, scheduler installation, roadmap/checkpoint edit, staging, commit, or push is part of this implementation package.

## Files inspected and reuse map

The implementation worker must reread the approved design and checkpoint before coding, then use these existing components as contracts:

- `reports/CODEX_SESSION_CHECKPOINT_2026_09_06.md` — current P0 burn-in/L2/L3 priority, canonical tree and runtime boundary.
- `docs/superpowers/specs/2026-09-06-lab-ai-v0-design.md` — authority string, V0A–V0D phases, answer contract, and Market Perception separation.
- `reports/OLLAMA_ROUTINE_BOUNDARY_2026_08_27.md` — existing local-model limits, bounded digest recommendation, and absence of human precision labels.
- `research_lab/research_conveyor_contract.py` — canonical JSON, duplicate-key loader, path guards, receipt self-hash, and atomic write primitive to reuse or wrap; do not weaken its research-only authority.
- `scripts/run_research_conveyor.py` — sanitized environment, bounded capture, process/resource guard patterns, and terminal receipt semantics.
- `research_lab/continuous_audit.py`, `research_lab/audit_registry.py`, and `research_lab/negative_outcome_registry.py` — deterministic audit findings, current/stale handling, review statuses, and negative evidence; their verdicts remain evidence to index, never automatic conclusions.
- `research_lab/experiment_lifecycle.py` and `research_lab/trial_ledger.py` — append-only experiment provenance, hash chains, pre-registration-before-result, and multiple-testing context.
- `scripts/chat_with_local_ai.py` and `research_lab/ai_auditor.py` — existing allowlist/context wording, qwen3:8b loopback call shape, three-proposal cap, and proposal-only parser; do not copy their broad historical source list or secret-sensitive runtime assumptions into V0A.
- `tests/test_research_conveyor_contract.py`, `tests/test_run_research_conveyor.py`, `tests/test_ai_auditor_model_payload.py`, `tests/test_chat_with_local_ai.py`, `tests/test_continuous_audit.py`, and `tests/test_negative_outcome_registry.py` — existing fail-closed, bounded, freshness, parser, and receipt test conventions.

## P0 ordering and resource gate

The execution owner must keep the following order visible in every V0 receipt and handoff:

1. P0 is the unchanged ATT1/ETS2S 72-hour burn-in, then burn-in receipt, L2 execution lifecycle parity, L3 fee/funding/accounting parity, and a clean zero-risk lifecycle shadow. No LAB_AI_V0 result can shorten or replace these gates.
2. V0A is the first LAB_AI slice and may use a lightweight local model after its deterministic pack passes. Its initial manifest fixes `max_total_input_bytes=1048576`, `max_source_bytes=262144`, `max_context_bytes=1048576`, `max_model_output_chars=16384`, `ollama_timeout_seconds=60`, and `max_threads=2`. If resources are contested, V0A yields and records `RESOURCE_GUARD`; it does not starve collectors or shadows.
3. V0B–V0D are follow-on technical gates and do not block trying the Tasks 1–3 vertical slice. Market Perception remains a separate research sandbox with its own budget, receipts, and evaluation.

### Task 1: Strict LAB_AI_V0 contract and immutable receipt primitives

**Files:**
- Create: `research_lab/lab_ai_v0_contract.py`
- Test: `tests/test_lab_ai_v0_contract.py`

**Interfaces:**
- Produces `RoutineManifest`, an immutable typed view of the manifest.
- Produces `load_routine_manifest(root: Path, path: Path) -> RoutineManifest`.
- Produces `load_strict_json(path: Path) -> Any` with duplicate-key and non-finite-number rejection.
- Produces `resolve_allowlisted_file(root: Path, relative_path: str) -> Path` with explicit-relative-path, root-containment, glob, and symlink checks.
- Produces `sha256_file(path: Path) -> str`.
- Produces `write_immutable_receipt(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]` and `read_verified_receipt(path: Path, expected_schema: str) -> dict[str, Any]`.

- [ ] **Step 1: Write failing contract tests.**

  Use temporary roots and assert that a manifest with unknown fields, duplicate source IDs, `../escape`, absolute paths, globs, symlinked files, symlinked parent directories, missing required fields, `NaN`, and `Infinity` raises `ContractError`. Assert that a valid manifest returns immutable copies and stable canonical SHA-256 values.

  ```python
  def test_duplicate_keys_and_symlink_escape_fail_closed(tmp_path: Path):
      duplicate = tmp_path / "duplicate.json"
      duplicate.write_text('{"schema_id":"x","schema_id":"y"}', encoding="utf-8")
      with pytest.raises(ContractError, match="duplicate"):
          load_strict_json(duplicate)

      target = tmp_path / "source.md"
      target.write_text("safe\n", encoding="utf-8")
      link = tmp_path / "linked.md"
      link.symlink_to(target)
      with pytest.raises(ContractError, match="symlink"):
          resolve_allowlisted_file(tmp_path, "linked.md")
  ```

- [ ] **Step 2: Run the focused tests and verify failure.**

  Run `pytest -q tests/test_lab_ai_v0_contract.py`. Expected result: import failure because the new contract module does not exist.

- [ ] **Step 3: Implement the minimal contract.**

  Parse JSON with `object_pairs_hook` that rejects repeated keys; use `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)` for hashes; reject non-finite values recursively; require exact top-level and nested field sets; resolve every source only after checking every path component for symlinks; and write a receipt to a fresh path using exclusive creation plus `fsync`. Reuse the canonical hashing semantics in `research_lab/research_conveyor_contract.py` where compatible, without importing private broker or runtime code.

- [ ] **Step 4: Run the focused tests and invariant checks.**

  Run `pytest -q tests/test_lab_ai_v0_contract.py` and `python3 -m py_compile research_lab/lab_ai_v0_contract.py`. Expected result: all contract tests pass and the module compiles.

### Task 2: V0A safe source manifest and deterministic context pack

**Files:**
- Create: `configs/local_ai_routine_digest_v1.json`
- Create: `scripts/build_local_ai_routine_digest.py`
- Test: `tests/test_local_ai_routine_digest.py`

**Interfaces:**
- Consumes `RoutineManifest` and the allowlisted existing reports/receipts/ledgers.
- Produces `collect_source(root: Path, spec: Mapping[str, Any], now: datetime) -> dict[str, Any]`.
- Produces `build_digest(root: Path, manifest_path: Path, output_dir: Path, *, now: datetime | None = None) -> dict[str, Any]`, returning the verified receipt plus `receipt_path` and `context_path` for the next task.
- Produces a bounded `lab_ai_v0_input_receipt_v1` containing manifest SHA, per-source path/SHA/mtime/schema/freshness/redaction outcomes, guard outcomes, and no model text.
- Test support defines `write_fixture_manifest(root: Path, source_path: str, max_bytes: int, tail_lines: int) -> Path` and `FIXED_NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)` so the focused tests do not depend on wall clock time.

- [ ] **Step 1: Write failing deterministic collection tests.**

  Cover stable ordering, source hashes, mtime freshness, required versus optional missing files, byte and tail caps, redaction, schema labels, and receipt citations.

  ```python
  def test_digest_is_deterministic_and_redacts_secret_like_text(tmp_path: Path):
      source = tmp_path / "report.md"
      source.write_text("status=ok\nAPI_KEY=do-not-copy\n" + ("x" * 100), encoding="utf-8")
      manifest = write_fixture_manifest(tmp_path, "report.md", max_bytes=64, tail_lines=2)

      first = build_digest(tmp_path, manifest, tmp_path / "runs", now=FIXED_NOW)
      second = build_digest(tmp_path, manifest, tmp_path / "runs", now=FIXED_NOW)

      assert first["schema_id"] == "lab_ai_v0_input_receipt_v1"
      assert first["sources"][0]["sha256"] == second["sources"][0]["sha256"]
      assert first["context_sha256"] == second["context_sha256"]
      assert "do-not-copy" not in json.dumps(first, ensure_ascii=False)
      assert first["sources"][0]["truncated"] is True
      assert first["invocation_id"] != second["invocation_id"]
      assert first["receipt_path"] != second["receipt_path"]
  ```

  Define `write_fixture_manifest` in the test module with the exact schema ID and authority from this plan, one `sources` entry using the supplied path/limits, and a `limits` object whose total input and output caps exceed the fixture. The helper writes only `manifest.json` beneath `tmp_path` and returns that path.

- [ ] **Step 2: Run focused tests and verify failure.**

  Run `pytest -q tests/test_local_ai_routine_digest.py`. Expected result: import failure because the digest script does not exist.

- [ ] **Step 3: Add the explicit manifest.**

  The manifest must use exact relative paths and strict per-source caps. Start with the current checkpoint, LAB_AI design, Ollama boundary, ATT1/ETS2S parity report, and the 2026-09-05 deployment receipt. Add explicit optional entries for the deterministic audit registry, negative-outcome registry, Trial Ledger, experiment lifecycle ledger, and Research Conveyor terminal receipts when present. Set the initial top-level limits exactly to `max_total_input_bytes=1048576`, `max_source_bytes=262144`, `max_context_bytes=1048576`, `max_model_output_chars=16384`, `ollama_timeout_seconds=60`, and `max_threads=2`. Each entry declares `source_id`, `path`, `format`, `required`, `max_age_seconds`, `max_bytes`, `tail_lines`, and a redaction policy. A physical source larger than `max_source_bytes` is not partially read: record `SOURCE_SIZE_OVERFLOW` and fail closed for a required source, or record `MISSING_OPTIONAL` with the guard reason for an optional source. `tail_lines` limits the selected excerpt only after the physical-size check; if the selected excerpt reaches its byte cap, record `TAIL_TRUNCATED` explicitly. The manifest records absent optional sources as `MISSING_OPTIONAL`; it never silently drops them. Do not include `.env`, key/certificate files, broker payloads, unrestricted runtime logs, or the legacy whole-project context.

- [ ] **Step 4: Implement deterministic collection.**

  Validate the manifest before reading any source. Enforce the cumulative 1 MiB input budget and the 256 KiB physical per-source limit before reading bytes. Read markdown as bounded UTF-8 text and JSON/JSONL with strict duplicate-key/nonfinite validation. Preserve only bounded tails or bounded sections declared by the source entry. Redact credential-shaped values and secret-bearing lines before storing or hashing the model-visible text; retain redaction counts and source SHA for the original file without retaining secret contents. Mark each row `CURRENT`, `STALE`, `MISSING_REQUIRED`, `MISSING_OPTIONAL`, `SUPERSEDED`, `SOURCE_SIZE_OVERFLOW`, `TAIL_TRUNCATED`, or `NOT_CONFIRMED` according to explicit manifest metadata and freshness checks. If two structured sources expose the same declared claim key with incompatible values, retain both citations and mark the group `NOT_CONFIRMED`; never choose a winner.

- [ ] **Step 5: Write and verify immutable input receipts.**

  Create `output_dir/<run_id>/digest.json` with a unique `invocation_id`, manifest SHA, source rows, bounded context payload, authority, resource counters, and self-hash. Refuse an existing `digest.json`; write a `BLOCKED_INPUT` receipt when a required source or guard fails. Keep the context pack and receipt separate so the pack can be discarded and the receipt can still prove what was attempted. With the same fixed `now`, the content/context hash and source rows must match across runs; run identity and receipt path may differ, and the implementation must not require differing self-hashes merely because the run paths differ.

- [ ] **Step 6: Run focused tests and inspect the exact diff.**

  Run `pytest -q tests/test_lab_ai_v0_contract.py tests/test_local_ai_routine_digest.py`, `python3 -m py_compile scripts/build_local_ai_routine_digest.py`, and `git diff --check`. Expected result: all focused tests pass, no secret-shaped fixture value appears in output, and only the planned files are changed.

### Task 3: One bounded, loopback-only Ollama proposal call

**Files:**
- Create: `scripts/classify_local_ai_routine_digest.py`
- Test: `tests/test_local_ai_routine_classifier.py`

**Interfaces:**
- Consumes a verified `lab_ai_v0_input_receipt_v1` and its bounded context payload.
- Produces `call_ollama_once(context: str, *, model: str, base_url: str, timeout_seconds: float, max_output_chars: int) -> tuple[str, dict[str, Any]]`.
- Produces `classify_digest(digest_path: Path, output_dir: Path, *, model: str = "qwen3:8b", base_url: str = "http://127.0.0.1:11434", timeout_seconds: float = 60.0) -> dict[str, Any]`.
- Produces a `lab_ai_v0_proposal_receipt_v1` with the verified input receipt hash, bounded model metadata, parsed proposals, citation-validation result, and authority zeros.
- Test support defines `FakeResponse` with context-manager methods and `read() -> bytes`, plus `write_verified_digest(tmp_path: Path) -> Path` that writes a valid Task 2 receipt fixture and verifies its self-hash before returning the receipt path.

- [ ] **Step 1: Write failing classifier and capability-boundary tests.**

  Stub `urllib.request.urlopen` and assert one request, loopback-only URL enforcement, no environment values in the request, max three proposals, strict JSON parsing, required falsification fields, source path/SHA citation checks, and immutable output receipt. Assert non-loopback URLs, duplicate model JSON keys, nonfinite values, malformed output, overlong output, and mutation-shaped proposals fail closed.

  ```python
  AUTHORITY = "local_readonly_secret_free_proposal_only_no_code_config_process_network_broker_order_risk_promotion_deploy_or_money_authority"

  def test_classifier_makes_one_bounded_loopback_call(monkeypatch, tmp_path: Path):
      calls = []

      def fake_urlopen(request, timeout):
          calls.append((request.full_url, timeout, request.data))
          return FakeResponse('{"proposals": []}')

      monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
      digest = write_verified_digest(tmp_path)
      receipt = classify_digest(digest, tmp_path / "runs")

      assert len(calls) == 1
      assert calls[0][0] == "http://127.0.0.1:11434/api/chat"
      assert receipt["proposals"] == []
      assert receipt["authority"] == AUTHORITY
  ```

- [ ] **Step 2: Run focused tests and verify failure.**

  Run `pytest -q tests/test_local_ai_routine_classifier.py`. Expected result: import failure because the classifier script does not exist.

- [ ] **Step 3: Implement the bounded call and parser.**

  Accept only `http://127.0.0.1:<port>` or `http://localhost:<port>` and append `/api/chat`; reject all other schemes/hosts. Send the system boundary, answer contract, exact source citations, and bounded digest as JSON. Set `stream=false`, low temperature, and a hard timeout. Parse only a strict JSON object with `proposals`; cap at three; require `hypothesis`, `evidence`, `falsification`, and citation objects containing an input source path and SHA. Reject numeric claims without citations and discard or fail closed on any field that could request a command, file write, network call, broker call, risk change, promotion, or deployment.

- [ ] **Step 4: Store the model result as untrusted immutable data.**

  Write only a self-hashed proposal receipt in a new run directory. Store bounded raw model text only when the receipt schema explicitly labels it `untrusted_model_text`; never make it a registry finding or verdict automatically. If Ollama is unavailable or a guard fails, write `MODEL_UNAVAILABLE` or `BLOCKED_CAPABILITY` with zero proposals and the verified input receipt hash.

- [ ] **Step 5: Run focused tests and boundary checks.**

  Run `pytest -q tests/test_local_ai_routine_classifier.py tests/test_ai_auditor_model_payload.py tests/test_chat_with_local_ai.py`, `python3 -m py_compile scripts/classify_local_ai_routine_digest.py`, and a repository search proving the new scripts contain no broker/order imports and no `.env` reads. Expected result: focused tests pass, exactly one stubbed request is observed, and all capability attacks fail closed.

### Task 4: Optional V0A command wrapper after the first vertical slice

**Files:**
- Create: `scripts/run_lab_ai_v0.py`
- Test: `tests/test_run_lab_ai_v0.py`

**Interfaces:**
- Produces `run_v0a(root: Path, manifest_path: Path, output_root: Path, *, model_enabled: bool, now: datetime | None = None) -> dict[str, Any]`.
- Produces CLI flags `--manifest`, `--output-root`, `--model`, `--base-url`, `--no-model`, and `--verify-only`.
- Consumes only Task 1–3 modules; it never launches a shell command or imports a broker/private API module.

This is a convenience wrapper after Tasks 1–3 have produced a usable deterministic pack and bounded classifier. It is not required to try the first V0A slice, and failure here does not block deterministic packing or local classifier experiments.

- [ ] **Step 1: Write failing orchestration tests.**

  Assert deterministic collection runs before any model call, `--no-model` performs zero network requests, `--verify-only` performs zero collection and network writes, a required-input failure prevents the model call, repeated runs create separate directories, and every emitted receipt verifies independently.

- [ ] **Step 2: Run the focused tests and verify failure.**

  Run `pytest -q tests/test_run_lab_ai_v0.py`. Expected result: import failure because the orchestrator does not exist.

- [ ] **Step 3: Implement the smallest command boundary.**

  Generate the deterministic pack first, verify its self-hash, then optionally call the classifier once. Return nonzero only for technical or guard failures; `MODEL_UNAVAILABLE` remains proposal-only and cannot be interpreted as a research verdict. Use no scheduler and no process spawning. Keep output under `runtime/lab_ai_v0/<run_id>/` only when the operator explicitly supplies that output root.

- [ ] **Step 4: Run V0A acceptance tests.**

  Run `pytest -q tests/test_lab_ai_v0_contract.py tests/test_local_ai_routine_digest.py tests/test_local_ai_routine_classifier.py tests/test_run_lab_ai_v0.py`, `python3 -m py_compile research_lab/lab_ai_v0_contract.py scripts/build_local_ai_routine_digest.py scripts/classify_local_ai_routine_digest.py scripts/run_lab_ai_v0.py`, and `git diff --check`. V0A is accepted only if all receipts verify, all citation paths stay within the manifest, no secret canary appears, one stubbed Ollama call is the maximum, and no mutation/capability escape is accepted.

### Task 5: V0B disposable DuckDB exact and lexical retrieval

**Files:**
- Create: `research_lab/lab_ai_catalog.py`
- Create: `scripts/build_lab_ai_catalog.py`
- Create: `tests/test_lab_ai_catalog.py`
- Create: `tests/fixtures/lab_ai_catalog_sources/` with non-secret markdown/JSON/JSONL fixtures only

**Interfaces:**
- Produces `build_catalog(input_receipt_paths: Sequence[Path], db_path: Path) -> dict[str, Any]`.
- Produces `search_exact(db_path: Path, query: str, *, limit: int = 20) -> list[dict[str, Any]]`.
- Produces `search_lexical(db_path: Path, query: str, *, limit: int = 20) -> list[dict[str, Any]]`.
- Produces `find_status_conflicts(db_path: Path, subject: str) -> list[dict[str, Any]]`.
- Every result includes source path, source SHA, section/line provenance, freshness state, and `NOT_CONFIRMED` when conflict evidence exists.

- [ ] **Step 1: Freeze a retrieval evaluation fixture before implementing search.**

  Include one current claim, one superseded claim, two incompatible claims for the same subject, one repeated experiment, one cost-killed edge, one data-leak marker, and one absent source. Hash the fixture manifest and record the expected exact/lexical result order.

- [ ] **Step 2: Write failing catalog tests.**

  Assert catalog rebuilds reproduce the same rows, exact search returns the cited source, lexical search is bounded and deterministic, conflicts return both sides, a changed source SHA invalidates the derived row, and the database contains no secret or authority field that could be mistaken for truth.

- [ ] **Step 3: Implement the derived index.**

  Read only verified V0A input receipts and source files whose SHA still matches. Store source metadata, chunks, structured facts, experiment IDs, trial counts, status, and provenance in DuckDB. Keep no canonical copy of reports in DuckDB; source files and receipts remain authoritative. Do not add Qdrant until exact and lexical retrieval have a frozen baseline and a measured failure mode.

- [ ] **Step 4: Run the V0B gate.**

  Run `pytest -q tests/test_lab_ai_catalog.py`, rebuild twice into disposable databases, compare canonical result receipts, and verify a tampered-source test yields `BLOCKED_INPUT` rather than stale retrieval. V0B may proceed only with a verified V0A receipt and a resource report showing no collector/shadow starvation.

### Task 6: V0C typed laboratory tools and answer validator

**Files:**
- Create: `research_lab/lab_ai_tools.py`
- Create: `scripts/query_lab_ai_v0.py`
- Create: `tests/test_lab_ai_tools.py`

**Interfaces:**
- `get_current_project_state(catalog_path: Path) -> dict[str, Any]`.
- `get_trial(catalog_path: Path, experiment_id: str) -> dict[str, Any]`.
- `compare_trials(catalog_path: Path, experiment_ids: Sequence[str]) -> dict[str, Any]`.
- `find_similar_failures(catalog_path: Path, query: str, filters: Mapping[str, str] | None = None) -> list[dict[str, Any]]`.
- `get_shadow_health(catalog_path: Path, shadow_id: str, time_range: Mapping[str, str]) -> dict[str, Any]`.
- `find_status_conflicts(catalog_path: Path, subject: str) -> list[dict[str, Any]]`.
- `draft_experiment_card(hypothesis: str, falsification: str, evidence: Sequence[Mapping[str, str]]) -> dict[str, Any]`.
- `validate_answer(answer: Mapping[str, Any]) -> dict[str, Any]`.

- [ ] **Step 1: Write failing typed-tool tests.**

  Assert only the seven allowlisted function names are callable, arguments are typed and bounded, arbitrary paths and commands are rejected, every result carries citations, stale/conflicting facts become `NOT_CONFIRMED`, and `draft_experiment_card` cannot write a file or alter the Trial Ledger.

- [ ] **Step 2: Run focused tests and verify failure.**

  Run `pytest -q tests/test_lab_ai_tools.py`. Expected result: import failure because the tool module does not exist.

- [ ] **Step 3: Implement read-only dispatch and answer validation.**

  Dispatch through a fixed dictionary of Python callables; reject arbitrary function names, file paths, shell text, URLs, and broker-shaped arguments. Require bounded JSON output, source path/SHA citations, explicit `inference` labels, conflict states, and a falsification condition. Keep `draft_experiment_card` in memory as proposal data; a separate deterministic human-review wrapper may persist a validated card while preserving the append-only review ledger.

- [ ] **Step 4: Run the V0C gate.**

  Run `pytest -q tests/test_lab_ai_tools.py tests/test_lab_ai_catalog.py tests/test_local_ai_routine_classifier.py`, then execute a fixture query for each tool and verify every numeric claim resolves to a source SHA. Any failed validation returns its receipt and keeps the system proposal-only.

### Task 7: V0D frozen evaluation, human labels, and quiet-operation gate

**Files:**
- Create: `tests/fixtures/lab_ai_v0_evaluation.json`
- Create: `scripts/evaluate_lab_ai_v0.py`
- Create: `tests/test_evaluate_lab_ai_v0.py`
- Create: `docs/superpowers/specs/2026-09-06-lab-ai-v0-operations.md` after the V0C technical receipt is clean

**Interfaces:**
- Produces `evaluate_v0(cases_path: Path, answer_receipts: Sequence[Path]) -> dict[str, Any]`.
- Evaluates citation resolution, stale/conflict handling, secret disclosure, capability escapes, deterministic-tool agreement, false positives, and false negatives.
- Does not report precision until at least 30 proposals have human labels from `confirmed`, `rejected`, `duplicate`, or `needs_data`.

- [ ] **Step 1: Write the frozen adversarial evaluation set.**

  Include current-state questions, superseded claims, incompatible metrics, repeated experiments, cost-killed edges, data-leak evidence, missing-source questions, secret-canary prompts, arbitrary-command prompts, broker/private-API prompts, and promotion/money prompts. Store expected citation IDs and expected `NOT_CONFIRMED`/capability rejection outcomes.

- [ ] **Step 2: Write failing evaluation tests.**

  Assert every numeric expected answer has a resolvable source path/SHA, stale or conflicting cases never resolve to a guessed winner, secret/capability attacks have zero accepted escapes, deterministic tools reproduce their expected values, and the report contains both false-positive and false-negative counts. Assert a run with fewer than 30 labels cannot emit a precision percentage.

- [ ] **Step 3: Implement the evaluator and label ledger.**

  Compare answers against deterministic tool outputs and frozen expected labels. Write an immutable evaluation receipt with case-level evidence, rejection reasons, label counts, resource use, and authority zeros. Keep human labels append-only and separate from model output; no model may label itself.

- [ ] **Step 4: Run the V0D gate.**

  Run `pytest -q tests/test_evaluate_lab_ai_v0.py tests/test_lab_ai_tools.py tests/test_lab_ai_catalog.py`, inspect the complete evaluation receipt, and require all acceptance conditions from the design: 100% numeric citation resolution, zero secret/capability escapes, explicit `NOT_CONFIRMED`, deterministic reproducibility, no mutation, 30 human labels before precision, false positives and false negatives, and resource caps. A failure keeps V0 proposal-only and returns the failing receipt.

- [ ] **Step 5: Specify quiet operation only after the gate.**

  Do not install a scheduler in this plan. A separate scoped task may add one local quiet schedule with explicit max runtime, max input/output bytes, local-only endpoint, lock, skip-on-contention behavior, and immutable receipts. The schedule must remain silent when unchanged and must notify only on completion, failure, meaningful state change, or required human action. Separate confirmation is required only if a future operation would touch money, risk, current positions, or sealed evidence consumption.

## Separate parallel project: Market Perception research sandbox

The owner authorized starting this research sandbox in parallel. It is deliberately separate from `LAB_AI_V0`: no V0A–V0D task imports it, no V0 receipt claims it was evaluated, and no trained adapter is approved by this plan.

The future sandbox should have a separate spec/plan and a separate subtree such as `research_lab/market_perception/`, with independent manifests, data hashes, experiment IDs, and receipts. Safe local analysis and scripts may begin in parallel under those boundaries. Its stages are:

1. **Market State:** causal, multi-timeframe, point-in-time state materialization with explicit missing-data and timestamp semantics.
2. **Pattern Memory:** exact and measured similarity retrieval over frozen historical states; derived indices are rebuildable and never truth.
3. **Regime/Drift:** classification of regime and drift with untouched evaluation windows and explicit uncertainty.
4. **Strategy Experts:** research-only classification/ranking of existing setups, beginning with `TAKE`/`SKIP` or ranked candidates. Every output must cite the state, pattern, and outcome sources.
5. **Meta Gate:** a proposal-only research gate whose output can be compared with matched controls; it cannot change strategy code, risk, slots, orders, or promotion state.
6. **Forecast research:** begin with cheap deterministic and statistical outcome-distribution or return-horizon baselines in its own frozen experiment track; this track is independent of classification/ranking/similarity results. Any learned forecast must pass its own causal replay, leakage tests, matched controls, drift evaluation, and prospective shadow. A price-prediction LoRA is explicitly deferred.
7. **Prospective shadow:** a frozen version runs zero-risk and records decisions, counterfactual outcomes, latency, missingness, drift, and incidents before any owner considers a micro-canary.

The sandbox may run classification, ranking, pattern-similarity, and cheap forecast baselines as separate preregistered experiments. It must preserve raw inputs, preregistration, controls, negative phenotypes, cost assumptions, and immutable receipts. No nightly retraining may trade a new version the next morning. No adapter, model, pattern score, forecast, or meta-gate output is a money authority.

Its resource policy is P0-aware: use an explicit local CPU/RAM/time budget, stop or skip on contention with market-data collectors, VPS shadows, burn-in evaluation, or V0A, and report `RESOURCE_GUARD` rather than degrading those systems. This sandbox may consume V0B derived evidence only through verified read-only citations after V0B passes; it must not write to the LAB_AI catalog or its human-review ledger.

## Acceptance gates and known gaps

Tasks 1–3 are ready for execution as the first vertical slice once their focused tests and deterministic receipts are in place. V0B–V0D are follow-on technical gates and do not block trying the deterministic pack. No date-based promotion exists; only an action that touches money, risk, current positions, or sealed evidence consumption requires separate explicit confirmation.

Known gaps to resolve in the relevant task rather than silently assuming away:

- The canonical tree currently has the Conveyor receipt primitives and several older AI surfaces, but no LAB_AI_V0 manifest, input receipt schema, DuckDB catalog, typed tool dispatcher, or frozen evaluation set. Those are planned new files.
- Existing `scripts/chat_with_local_ai.py` includes a broad historical allowlist and deterministic status text that contains older facts; V0A must use its own manifest and current source receipts rather than copying those assumptions.
- Existing `research_lab/ai_auditor.py` writes replaceable daily files and accepts a three-finding model payload; V0A must add write-once receipts, citation validation, and explicit capability rejection before using any model output.
- Runtime Trial Ledger, lifecycle ledger, audit registry, and current shadow receipts may be absent in a clean checkout. The manifest must record their absence and classify required versus optional evidence explicitly.
- Qdrant has no promotion eligibility from this plan. It requires a measured improvement over exact/lexical retrieval on the frozen set without loss of provenance.
- MLX-LM QLoRA is V1 only: it requires at least 500 human-reviewed training examples and 100 untouched evaluation examples, uses the exact base model it was trained against, passes the same frozen evaluation set, and remains proposal-only.
- The plan does not authorize VPS movement, scheduler installation, adapter training, runtime deployment, money, risk, order, promotion, Git staging, commit, or push.

No roadmap or checkpoint file is changed by this plan. Implementation should follow the task order above, using deterministic technical receipts at each gate. Separate explicit confirmation is reserved for money, risk, current-position, or sealed-evidence actions.
