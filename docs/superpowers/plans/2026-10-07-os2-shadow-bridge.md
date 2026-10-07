# OS2_SHADOW_BRIDGE_V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire existing regime/rank/gate/exposure/journal/diagnostic modules into an isolated, reproducible orders-OFF assessor.
**Architecture:** A pure closed-data/candidate assessor consumes a bounded source bundle. A single locked hash-chain journal commits the complete assessment and reservation state atomically. A one-shot CLI reads only the dedicated observer inbox; no broker, live caller, env overlay or model transport exists.
**Tech Stack:** Python stdlib, existing bot modules, pytest; no new dependencies.
**Spec:** `docs/superpowers/specs/2026-10-07-os2-shadow-bridge-design.md` (owner approved October7, including four additional constraints).

## Global Constraints

- Continue recovery733f014/current checkout; preserve the foreign untracked allowlist.
- No broker/client/credentials/order/model/strategy-config path. Every candidate money_authorized=False.
- No real policy authority before repaired B3: FIXTURE mode only exercises routing; EXTERNAL_PUBLIC returns POLICY_UNAPPROVED and cannot reserve slots.
- One canonical REZHIM_V1 envelope, derived from closed BTC H1 constituents; do not read alternate env/json states or apply legacy override dictionaries.
- Current Alpaca/ATT1/KITY sources, evidence, money gates and original deadlines remain unchanged; their due work preempts this plan.
- No fresh historical or sealed outcome/judge consumption, Claude checkout edits, whole-branch merge or cleanup.
- Native implementation is authorized by the owner's explicit proceed instruction; one fresh financial/security review at delivery.

## Concrete Bounds

- Input2MiB, max800H1 bars (last200 closed4h, minimum60), max64events/bundle.
- Max source-observation age300000ms, clock uncertainty0..250ms; availability/closure must be no later than decision's conservative cutoff. Latest completed4h cutoff must equal floor((decision_ms−uncertainty)/14400000)*14400000.
- Every selected4h group has four unique consecutive UTC-aligned H1 bars; finite positive OHLC, nonnegative volume, coherent high/low, no gaps/revisions/future members.
- Dedicated journal8MiB/4096receipts, max2MiB append,2 files (lock/journal), minimum free disk536870912bytes plus next append. Startup read bounded by8MiB; no repeated full scan within one process. One-shot assessor deadline30s.
- Synthetic fixture policy: max3slots, max2same-side, max1beta-cluster; corr threshold0.6, cluster risk1.5%, scale OFF. These are fixture units, not approved live caps. Complete correlation/position source required; unknown is not zero.
- No timers/services launched. Runtime path is dedicated `runtime/os2_shadow_bridge_v1`; CLI input restricted to its inbox or `.private/os2_shadow_bridge_v1` fixture area.

## Review Focus

- Missing correlation or position provenance must reject, not default to diversification.
- Late/partial/future bars and UNKNOWN must not masquerade as valid NEUTRAL.
- Same intent with changed source/clock/body must conflict, not reprice or allocate again.
- A crash/corrupt append or symlink/hardlink must never rewrite another journal or drop durable reservations.
- A terminal with wrong owner/source, gap, missing costs/finality or duplicate must not free a slot or enter health statistics.

### Task1: Causal regime envelope and pure admission

**Files:** Create `research_lab/os2_shadow_bridge.py`; test `tests/test_os2_shadow_bridge.py`.
**Interfaces:** `assess_bundle(bundle: dict, state: dict) -> dict` returns `{status,reason,regime_envelope,decisions,state_after,diagnostics}`; `empty_state() -> dict`. Identity/source SHA comes from canonical JSON; envelope computed once and referenced by hash in all decisions.

- [x] Write failing tests for valid closed4h parity; missing/duplicate/future/NaN/late/clock uncertainty; UNKNOWN vs NEUTRAL; unapproved external policy; complete exposure; overlap/cooldown/occupied slots.
- [x] Run `.venv/bin/python -m pytest -q tests/test_os2_shadow_bridge.py` and observe missing implementation failure.
- [x] Implement bounded validation, reuse compute_regime labels only, StrategyCandidate, rank_candidates and strategy_regime_gate. Rank one sorted candidate at a time against evolving shadow slots; check exposure before reserving so a rejection does not consume a slot. All no-signal/invalid/rejected events receive decisions.
- [x] Add source-bound exact-owned fixture terminals (clean continuity, costs_complete/finality, finite netR, terminal time≤cutoff); duplicates cannot free/count twice. Preserve source domains; no external-policy terminals counted as fixture economics.
- [x] Run targeted tests; record RED/GREEN and commit explicit paths.

### Task2: Durable separate decision journal and advisory diagnosis

**Files:** Create `research_lab/os2_shadow_journal.py`; test `tests/test_os2_shadow_journal.py`.
**Interfaces:** `ShadowJournal(root: Path).process(bundle: dict) -> dict` locks, validates chain/state and commits one complete receipt+state; repeat request_id/same hash returns exact saved receipt. Changed payload same ID raises `BridgeBlocked`. `BridgeBlocked(status: str, reason: str)` also covers malformed sources and resource suspension.

- [x] Write failing tests for restart/reservations, duplicate/conflict, partial/hash-invalid tail, lock contention, byte/inode/disk bounds, symlink/hardlink and terminal duplicate/finality rejection.
- [x] Observe RED before implementation. Reuse decision_bus.build_decision serialization with finite fields; do not use its unguarded append/read as a durability primitive.
- [x] Implement O_NOFOLLOW regular-owned files, flock, canonical JSON hash chain, append+fsync before success, bounded startup replay and full state transaction. Uncertain append poisons this instance; reopen/read exact prefix instead of reapplying an intent. Never truncate/repair corruption or write baseline state.
- [x] Feed only accepted source-bound fixture terminal netR into existing edge_monitor and research_orchestrator; outputs strictly proposals with evidence_kind=FIXTURE/no money authority. Exclude unresolved/gap/duplicate outcomes and label insufficient sample.
- [x] Run new+dependency targeted tests; record RED/GREEN and commit.

### Task3: One-shot CLI, review and terminal delivery

**Files:** Create `scripts/run_os2_shadow_bridge.py`, `tests/test_os2_shadow_cli.py`, `reports/OS2_SHADOW_BRIDGE_RUNBOOK_2026_10_07.md`, delivery MD/JSON; update canonical checkpoint/handoff/roadmap/AGENTS.
**Interfaces:** CLI `--input <dedicated-inbox.json> [--runtime-dir <dedicated namespace>]`; status JSON stdout and exit0 SHADOW_WIRING_PASS, exit2 BLOCKED_DATA, exit3 BLOCKED_IMPLEMENTATION. No polling, secret read, alternate runtime or transport option.

- [ ] Write/observe failing CLI tests: input/runtime path refusal, NaN/duplicate JSON key/oversize, EXTERNAL_PUBLIC rejection, no broker/model/env access.
- [ ] Implement bounded source read, monotonic30s guard and journal invocation. Preserve one canonical envelope inside receipt; no second env/file authority.
- [ ] Run targeted suite and guarded full suite; compare failures by exact name against recorded baseline, preserve foreign diff and list all existing failures in delivery JSON.
- [ ] One fresh6-astra/high review of whole scoped diff; reproduce any important finding RED, fix one bounded pass and verify affected+regression tests.
- [ ] Produce terminal SHADOW_WIRING_PASS / BLOCKED_DATA / BLOCKED_IMPLEMENTATION for the candidate, with source/verification limits; no actual-account/canary/profitability claim. Commit/push explicit files and verify remote.

## Execution Ledger

- BASE733f014. Spec review and explicit implementation GO received; no extra stage approval inferred for LIVE.
- Ruling: implement native in established recovery checkout — user repeatedly requested continuation here; foreign file is isolated/preserved. No new worktree or sibling mutation.
- Ruling: fixture-only routing until B3 evidence; actual data can be assessed for provenance but cannot reserve or promote policy.
- Ruling: persistence is a small isolated wrapper around existing decision records, not a new production orchestration framework.
- Plan self-review: contracts, quotas, five failure classes and explicit money boundary covered by Tasks1–3. Ollama worker/deployment/B3 repair remain separate scopes.

Task1: RED missing module confirmed; GREEN31 new behavior cases,69 including reused dependencies. No market archive/judge/account consumption.

Task2: RED missing journal confirmed; GREEN14 durable restart/corruption/security/resource cases. Task3 CLI RED absent script; GREEN7 cases. All90 candidate+dependency tests PASS before review.

Final bounded review: verified6-astra/high at29b4156 found4 reproducible causal/state issues. All reproduced RED and fixed once: intent→source timing/reference, terminal after stored admission/trusted side, all observed ID hashes,800-hour revision retention. Added side-specific registry/advisory diagnostics, unique denominators and same-size journal edit guard. GREEN114 candidate+dependency tests; final guarded full suite pending. No second review/strategy research or money authority.
