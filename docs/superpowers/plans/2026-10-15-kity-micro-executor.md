# KITY micro execution lifecycle implementation plan

> **For agentic workers:** Execute inline using superpowers:executing-plans;
> preserve the repository's root-only review/quota restriction. No new workers.

**Goal:** implement and test the isolated ten-leg execution state machine under
the owner's $210 gross / $15 all-in /30min /20.3% rounding preparation bounds.

**Architecture:** extend the existing no-send KITY preparation with an isolated
SQLite event journal and deterministic action planner. Reuse canonical hashing,
Decimal and book-VWAP primitives; never import the monolith. The real-money
boundary refuses entry while an absolute $15 final-loss guarantee is unsupported.

**Tech Stack:** Python stdlib, SQLite FULL synchronous, existing pytest/Decimal.

**Spec:** ../specs/2026-10-15-kity-execution-micro-live-v1-design.md plus the direct
owner reply to call_97d470124f1e40728c7172870f18ac54.

## Global constraints

- Exact original ten symbols and sides; separate EXECUTION_MICRO_LIVE ledger.
- Gross≤210USDT; requested hard all-in loss≤15USDT; duration1800000ms;
  per-leg floor-rounding shortfall≤0.203. No silent relaxation of hard loss.
- No entries before separate exact GO. No averaging/scaling/re-entry.
- No runtime/account/mode/leverage writes, source changes or research outcomes.
- Micro PnL cannot enter KITY research/C1–C3/KEEP-KILL.
- Today's Alpaca opening retains priority and its frozen code/schedule.

## Review focus

- Crash after intent but before ACK: replay retains uncertainty, never resends.
- Duplicate executionIDs under new eventIDs: no double quantity/fees/PnL.
- Partial entry/exit or late fill: no guessed holdings or false flat/finality.
- Loss accounting: actual fill prices already include slippage; no double debit.
- Restart/time/cost gaps: original deadline survives; unknown is never zero.

## Task1 — owner bounds and exact readiness boundary

Files: configs/research/kity_execution_micro_owner_bounds_20261015.json,
research_lab/kity_execution_micro_runtime_v1.py, tests/test_kity_micro_runtime_v1.py.

- [x] Write failing tests for owner bounds, exact210 ceiling,0.203 rounding,
  immutable ten-leg identities and refusal to reinterpret hard15 as a stop trigger.
- [x] Implement `prepare_micro_plan(dossier,bounds)` as no-send exact plan builder
  and `assess_micro_readiness(plan,account)` with current hard-loss refusal.
- [x] Verify targeted tests. Preserve old source/intake/policy receipts unchanged.

## Task2 — durable lifecycle and all-in liquidation accounting

Files: same runtime/test pair. Interfaces: `MicroJournal(path,plan)`,
`append(event)`, `snapshot()`, `actions(now_ms)`, `liquidation_value(...)`.

- [x] Write failing restart/duplicate/conflict/partial/reject/unknown-send tests.
- [x] Implement hash-chained append-only SQLite journal. Validate transitions
  before transaction commit. Default actions propose commands only; no transport.
- [x] Write/implement clock, source-cost UNKNOWN, full10→exit and finality tests.
- [x] Enforce owned reduce-only exit quantity and terminal readback before retry;
  retain explicit UNKNOWN/recovery when order or fill state is unresolved.
- [x] Verify synthetic lifecycle, not a real PAPER or broker execution PASS.

## Task3 — no-send operational interface and delivery

Files: scripts/run_kity_execution_micro_v1.py, matching CLI tests, delivery report,
owner amendment/evidence receipt, canonical checkpoint.

- [x] CLI preview/replay must not load credentials/create reservation/send orders.
- [x] Publish exact constraints, current saved-price cap result, practical loss
  trigger vs requested guarantee, runtime integration limitations and next action.
- [x] Run targeted tests and saved real-source replay; root-review the change.
- [x] Scoped commit/push; preserve unrelated untracked file and all old pins.

## Execution ledger

Base: af8b074. Existing Codex recovery checkout reused; Claude checkout separate.
Ruling: no real transport activation is implemented while hard-loss final-value
constraint cannot be established on the observed cross-margin perpetual account.
This preserves the user's limit rather than treating it as permission for overshoot.
Ruling:30min is anchored at the first persisted entry-send intent, conservatively
before any possible fill; restart cannot move the deadline later. Close latency
is measured, not promised zero. A failed close remains recovery-required.
Ruling: quantities/cost templates from the morning capture remain expired;
the same source may be replayed offline, never reused as a fresh trading quote.

Execution complete locally:462 targetedPASS;64 new lifecycle/adapter/CLI tests.
RED before new runtime/adapter/CLI modules; additional root counterexamples
failed before fixes and passed after. Real-source preview exactly matches under
network denial. Real readiness remains BLOCKED_EXECUTION under the owner hard
final-loss requirement; all old source pins preserved, no money or broker write.
