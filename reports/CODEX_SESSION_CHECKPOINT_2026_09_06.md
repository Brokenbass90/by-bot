# Codex session checkpoint — 2026-09-06

## Start here

Canonical tree: `bybit-bot-recovery-20260824`
Canonical branch: `codex/recovery-20260824`
Runtime release commit: `773ce065270b5df16041e49e0985c5e950e5da10`
Deployment-evidence commit: `d323a927cf76ea2c27f61932462ca14911ce0b6b`

Read in this order:

1. this checkpoint;
2. `reports/ATT1_ETS2S_VPS_SHADOW_2026_09_05.md`;
3. `research_lab/results/att1_ets2s_vps_shadow_20260905/deployment_receipt.json`;
4. `reports/CURRENT_PROJECT_ROADMAP.md`;
5. `docs/superpowers/specs/2026-09-06-lab-ai-v0-design.md`.

Older dated handoffs are history. When their status conflicts with this file,
use this file and then verify drift-prone live facts directly.

## Current outcome

The public-only ATT1/ETS2S fixed-51 signal shadow is deployed on the VPS and is
inside its 72-hour burn-in. It has no private API, broker, order, risk,
promotion or money authority. The deployment did not change the existing money
runtime and did not stop the old ATT1/SBR1 shadow timers.

Burn-in:

- start: `2026-09-05 08:02 UTC`;
- evaluate no earlier than: `2026-09-08 08:02 UTC`;
- latest checked cycle: `2026-09-06 03:02 UTC`;
- timer: active and enabled;
- latest service: `success`, exit `0`;
- both legacy ATT1 fixed-51 and SBR1 zero-risk timers: active.

Latest cumulative journal snapshot:

- 102 `ALPHA_FORWARD_BACKFILL` rows;
- 2,000 `EXECUTION_FORWARD` rows from 20 scheduled cycles;
- 2,102 total rows;
- 0 exceptions;
- 0 broker calls;
- 0 order calls;
- 0 private/money/order authority.

Observed raw signals across those 20 forward cycles:

- ATT1: 5;
- ETS2S: 13;
- total: 18;
- all observed sides: short.

These are signal rows, not 18 independent hypothetical trades. Repeated
signals while a setup remains valid require L2 position-lifecycle and dedup
semantics before trade-count or economics interpretation.

`HFTUSDT` remained in the fixed-51 configured/available universe but had no new
closed H1 bar in each checked cycle, so each cycle correctly wrote 50 decisions
per sleeve. This is current dedup behavior, not a silent universe change.

## What has been proven

- Canonical closed-bar/timeframe Store contract: PASS.
- ATT1 direct-strategy versus shadow L1 parity: 600/600 decisions, 6 signals,
  0 mismatches, 0 exceptions.
- ETS2S L1 parity: 600/600, 30 signals, 0 mismatches, 0 exceptions.
- Local scoped suite: 100 passed.
- Independent deployment/contract review: spec PASS, code-quality PASS, no
  remaining P0/P1 finding.
- Target config, manifest and launcher SHA match the root-owned deployment
  anchor.
- Bootstrap, restart/idempotency and first scheduled execution-forward cycle:
  healthy.

This proves the L1 public signal path is reproducible and operational. It does
not prove strategy profitability or grant promotion.

## P0 — shortest path toward money

1. Let the exact deployed release run unchanged through the 72-hour boundary.
2. At/after `2026-09-08 08:02 UTC`, produce one burn-in receipt covering every
   scheduled cycle: freshness, coverage, gaps, exceptions, hash-chain,
   restarts, resource use and authority zeros.
3. Build L2 execution-lifecycle parity: signal admission, same-bar/repeated
   signal dedup, one-position semantics, entry/order plan, partial/non-fill,
   stop/TP/trailing/time-stop and terminal exit. Keep it public-only and
   zero-risk first.
4. Build L3 accounting parity: actual fee/funding schedule, slippage contract,
   quantity/rounding, realized/unrealized ledger and restart reconciliation.
5. Run the L2/L3 lifecycle as zero-risk shadow and require a new clean receipt.
6. Only after those gates may an explicit owner-approved micro-canary be
   proposed. Nothing promotes automatically by date.

## P1 — project truth and LAB_AI_V0 in parallel

The owner approved the architecture on 2026-09-06. Written design:
`docs/superpowers/specs/2026-09-06-lab-ai-v0-design.md`.

The selected approach is a thin, read-only evidence assistant using the
existing Ollama/audit/ledger/conveyor components. It starts with deterministic
catalog and typed tools; DuckDB is the derived structured index, Qdrant is
conditional on retrieval evaluation, and MLX-LM QLoRA follows only after a
human-reviewed dataset exists.

It is parallel work for lighter models and must not delay P0. Ollama remains
secret-free and proposal-only. It cannot write code/config, run arbitrary
commands, contact brokers, change verdicts or receive money authority.

## P2 — research/data platform

After V0 proves basic factual retrieval:

- unify experiment identity, provenance, negative phenotypes and trial results
  in one machine registry;
- use DuckDB/Parquet for large market data and experiment queries;
- add Polars where lazy streaming materially reduces RAM/time;
- add Qdrant as a rebuildable semantic index, never as truth;
- consider DVC/MLflow compatibility without creating a competing authority;
- allow Optuna only in discovery/train with every trial logged and no OOS
  objective or automatic promotion.

## P3 — research model and market perception

First train a `researcher` adapter to distinguish valid tests, leakage, cost
artifacts, duplicates and missing evidence. Do not train the first LoRA to
predict price.

Market Perception is a later independent project:

`Market State -> Pattern Memory -> Regime/Drift -> Strategy Experts -> Meta Gate -> Shadow`.

It may improve setup selection and strategy routing, but must pass causal
replay, matched controls, drift evaluation and prospective shadow like every
other candidate.

## P4 — market sleeves after the critical gates

- Crypto: L2/L3 ATT1/ETS2S first; Bull Continuation and XSEC remain the next
  frozen research families.
- Alpaca: separate SAFE_HOLD track until current broker/service/deployed-SHA,
  selector/PIT and gap/restart/partial-fill lifecycle are reverified.
- XAU/Forex: unchanged-replication plan after causal data/cost parity, demo or
  zero-risk before money.
- Polymarket/DeFi/arbitrage: research-only inventory, settlement/cost/liquidity
  and execution-risk contracts before any wallet or order authority.

## Non-negotiable boundaries

- Do not modify the deployed shadow during its burn-in.
- Do not call raw signal count a trade count or profitability result.
- Do not increase risk, slots or money authority from L1 evidence.
- Do not use old ATT1/SBR1 OOS v1 for promotion; ATT1 was `FAIL_CLOSED`, SBR1
  `INCONCLUSIVE_LOW_N`.
- Do not use AI text as a verdict or source of numeric truth.
- Do not bulk-merge or bulk-clean `bybit-bot-clean-v28`.
- Do not use `git add -A`; stage exact reviewed files.

## Delegation model

Strong model:

- L2/L3 contracts and causal semantics;
- independent reviews and interpretation;
- capability/money boundaries;
- live deployment and promotion decisions.

Lighter Codex/Claude tasks:

- scoped implementation from approved plans;
- frozen runners, fixtures and deterministic tests;
- catalog adapters and documentation;
- source manifests, schema validation and report assembly.

Ollama:

- cited read-only search, anomaly grouping and proposal drafting;
- no code mutation, deployment, experiment verdict or trading decision.

## Exact next task

Until the 72-hour boundary, do not alter the deployed release. Prepare the
read-only burn-in evaluator and, in a separate scoped plan, the L2 execution
lifecycle contract. In parallel, review the LAB_AI_V0 design and write its
implementation plan only after owner review of the written specification.

At the boundary, evaluate burn-in before claiming completion. Then proceed to
L2; do not jump directly from L1 signals to a micro-canary.
