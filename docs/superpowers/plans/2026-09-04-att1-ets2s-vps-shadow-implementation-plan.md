# ATT1 + ETS2S VPS Shadow Implementation Plan

**Goal:** Run the L1-parity-proven ATT1 and ETS2S decision engines on an isolated, public-data-only VPS timer and start a 72-hour operational burn-in without orders, private APIs, or money authority.

**Spec authority:** Owner-approved design in the 2026-09-04 Codex task; L1 contract and evidence in `reports/ATT1_ETS2S_SIGNAL_SHADOW_PARITY_2026_09_04.md` and `research_lab/results/att1_ets2s_signal_shadow_parity_20260904/receipt.json`.

**Global constraints:**

- Do not alter live risk, orders, money authority, existing ATT1 money behavior, or Alpaca.
- Accept public Bybit market data only. Reject private endpoints and imports from broker/order modules.
- Evaluate only newly closed H1 bars. Build H4/D1 through the canonical closed-bar `Store` contract.
- Keep bootstrap/backfill evidence separate from timely execution-forward evidence.
- Fail closed on stale/gapped data, clock skew, source/config hash drift, journal corruption, or duplicate decision keys.
- Deployment is atomic and reversible. A local PASS is not a VPS PASS.

## Task 1: Freeze the public shadow contract

Create a default-off config/manifest with the fixed-51 evidence universe, source closure, explicit authority, public endpoint allowlist, data freshness/gap policy, journal paths, and literal operator acknowledgement.

Verification: contract tests reject enabled-without-ack, private capabilities, universe/hash drift, and unsafe output paths.

## Task 2: Implement canonical cached public feed and append-only ledger

Implement paginated H1 bootstrap plus incremental updates. Drop forming bars, validate continuity, persist atomically, and feed the canonical `Store` for H1/H4/D1. Write one idempotent row per `(sleeve_id, symbol, bar_ts)` including no-signal and exception outcomes. Classify rows as `ALPHA_FORWARD_BACKFILL` or `EXECUTION_FORWARD`.

Verification: TDD covers forming-bar exclusion, H4/D1 aggregation, stale/gap rejection, deterministic dedup, restart recovery, corrupted journal failure, and backfill/forward separation.

## Task 3: Wire ATT1 and ETS2S L1 engines

Use the exact L1-proven strategy profiles and source hashes. Evaluate both engines from the same canonical feed without importing live order paths. Emit stable decision payloads and per-cycle receipts/heartbeat.

Verification: fixture replay reproduces the accepted L1 receipt counts/hashes; forbidden-import and public-only tests pass.

## Task 4: Package hardened systemd runtime

Add a oneshot service and timer in an isolated `/opt/bybot-research/att1-ets2s-signal-shadow` runtime, with write access only to its runtime directory. Include preflight mode, explicit ack, source closure verification, clock/disk/heartbeat guards, and rollback instructions.

Verification: local dry-run and systemd artifact checks pass; no service is enabled locally.

## Task 5: Atomic VPS deploy and first-cycle verification

Upload the exact verified closure to a staged release, run target-Python import/startup/preflight smoke, activate atomically, verify deployed SHA/config hashes, enable the timer, and capture the first scheduled receipt. Do not count bootstrap rows as forward.

Verification: remote service/timer state, heartbeat freshness, deployed SHA, journal idempotency, gap/exception counts, and rollback target are all captured in a deployment receipt.

## Task 6: Start burn-in and publish handoff

Declare burn-in start only after the first healthy scheduled `EXECUTION_FORWARD` cycle. Publish current counts and exact gates for the 72-hour completion, L2 execution parity, L3 accounting, and eventual micro-canary.

Verification: a single report links local tests, remote receipt, release SHA, burn-in start timestamp, and any remaining blockers.
