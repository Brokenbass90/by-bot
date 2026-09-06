# ATT1/ETS2S read-only burn-in evaluator implementation plan

**Goal:** Produce a deterministic local progress/final receipt from a coherent read-only VPS snapshot, without touching the deployed release.

**Authority:** The owner explicitly authorized safe local research tools and read-only VPS checks on 2026-09-06. No money, risk, order, deployment or sealed-evidence authority. Work in the clean canonical recovery checkout; only new evaluator/test/doc files are in scope.

**Spec:** `reports/CODEX_SESSION_CHECKPOINT_2026_09_06.md`, P0 and exact next task; deployed contract is pinned by `research_lab/results/att1_ets2s_vps_shadow_20260905/deployment_receipt.json`.

## Interface and source bundle

Add `research_lab/att1_ets2s_burnin.py`, `scripts/evaluate_att1_ets2s_burnin.py`, and `tests/test_att1_ets2s_burnin.py`. The evaluator consumes an offline snapshot directory and the original deployment receipt, never calls SSH/network and never instantiates the journal writer. It writes one new output path exclusively or prints JSON to stdout. Existing inputs and output receipts cannot be overwritten.

The snapshot contains byte-preserved `events.jsonl`, `heartbeat.json`, `config.json`, `manifest.json`, `anchor.json`, `systemd.jsonl` (journalctl JSON), and `snapshot.json`. Snapshot metadata contains capture time, file SHA256/byte counts, service/timer properties, current disk bytes, source closure per-file hashes, launcher/unit hashes and a before/after consistency check. Every JSON parser rejects duplicate keys and non-finite values; missing or malformed required evidence fails closed. No secret/private log enters the bundle.

## Rules

- Validate the entire journal from genesis using its canonical row-hash contract, exact claim/payload correspondence, unique claims, valid streams, strict zero-authority fields, known profile/source hashes and fixed universe. Do not count raw signals as trades.
- Cross-check every cycle receipt parsed from systemd MESSAGE with journal rows: coverage, streams, signal/no-signal/exception counts, rows written, cumulative row count and chain tip. Include failed and zero-row invocations; do not silently drop malformed JSON receipts or service failures. Restarts cannot inflate scheduled hours.
- Verify every required hourly slot from `2026-09-05T08:02:00Z`. The 72-hour endpoint is `2026-09-08T08:02:00Z`; require 72 completed slots in the half-open start/end interval AND an as-of time at/after the endpoint. Later cycles are reported separately. A current in-flight slot has up to the deployed 20-minute service timeout before being classified missing. Missing earlier slots fail the gate.
- Validate each forward row against the pinned 300000 ms decision/forward-lag policy, causal H1 timestamps, and cycle observation time. The existing runner records observation at cycle START, not decision emission; preserve this limitation and report observed processing latency separately. L1 freshness does not establish executable fill latency.
- Require per-sleeve coverage over the fixed-51 universe with explicit unchanged/expected-unavailable accounting. HFTUSDT may remain unchanged as explicitly declared; no other missing symbol is silently exempted. Bootstrap/backfill rows never start or extend burn-in.
- Verify config, manifest, source closure, launcher and installed units against the deployment anchor/manifest and original receipt. No auto-update of pins.
- Report service failures/restarts, duration/CPU observations, current disk guard and missing historical resource measurements honestly. Do not invent RAM measurements; insufficient mandatory resource evidence prevents a final PASS. Peak RAM was not a deployed mandatory measurement; report its absence as a limitation, not a new historical gate.
- Status vocabulary: `IN_PROGRESS` before boundary if all available checks pass; `FAIL_CLOSED` for integrity/coverage/authority/source failures; `NOT_CONFIRMED` for insufficient mandatory evidence; `PASS_OPERATIONAL_BURN_IN` only for complete evidence at the boundary. Promotion/money authority is always false.

## Execution

- [x] Write behavioral tests that reject a tampered/truncated/duplicate journal, missing cycle, wrong profile/universe/authority, stale/future decision, misleading bootstrap, duplicate/restart hour inflation, missing systemd receipts, mismatched chain tip and pre-boundary PASS. A synthetic valid 72-hour bundle is the positive case.
- [x] Run `.venv/bin/python -m pytest -q tests/test_att1_ets2s_burnin.py`; verify failures before implementation.
- [x] Implement the pure evaluator and CLI; keep bounded input sizes and regular-file/no-symlink checks. No imports with live or journal-write side effects.
- [x] Run the focused suite and original journal/runner/contract suite.
- [x] Strong-model review of false-PASS paths; repair reproduced findings and rerun affected tests.
- [ ] Evaluate today's snapshot, preserve input hashes and receipt, update the canonical checkpoint with precise current findings and boundary command.

This cycle does not deploy L2, rerun a strategy against sealed windows, or claim economics from operational health.

## Execution status

29 evaluator tests passed, including reproduced false-PASS regressions and offline/in-memory equivalence. CLI/new receipt creation is verified. The aggregate VPS check succeeded; full raw export was rejected by approval review. The reviewed onsite alternative keeps raw data in VPS memory and returns only the aggregate receipt, but sending evaluator/deployment bytes requires specific destination approval, now requested. No rejected transfer/run executed. Original release remains unchanged.
