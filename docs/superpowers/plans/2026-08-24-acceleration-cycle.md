# Trading Station Acceleration Cycle Implementation Plan

> **For Codex:** execute with test-driven development and verification-before-completion. The approved source of truth is `reports/CODEX_SESSION_CHECKPOINT_2026_08_24.md` plus the owner approvals in the 2026-08-24 task.

**Goal:** Compress calendar time without expanding money authority: harden Alpaca observability and whole-share paper simulation, start interpretable SBR1 evidence, specify the existing XAU/MT5 demo path, and preserve all scoped work in the canonical recovery branch.

**Architecture:** Money routes remain fail-closed. Deterministic tools may observe, simulate, preregister, and emit hash-bound receipts; no new component may send orders or promote itself. Evidence universes are broad and free of risk, while money universes stay separately gated and narrow.

**Tech stack:** Python 3, pytest, shell launchers, JSON/JSONL receipts, existing Alpaca/Bybit/MT5 adapters.

---

### Task 1: Reproduce the safety baseline

- Run targeted Alpaca, parity, SBR1, and auto-apply tests.
- Run the standalone stop-floor invariant outside pytest collection.
- Record any packaging-only failure separately from strategy or protection failures.

### Task 2: Build the deterministic Alpaca health auditor

**Files:** `scripts/alpaca_health_auditor.py`, `tests/test_alpaca_health_auditor.py`, optional read-only launcher.

- First add failing tests for complete stop coverage, monotonic floor reconciliation, stale schedules/candidates, source hash mismatch, money-authority flags, hash-bound receipt, and failure exit status.
- Implement only GET/file/stat/hash logic. No order, cancel, replace, close, or entry methods.
- Keep Telegram as alert-only and make missing alert credentials non-fatal to evidence generation.

### Task 3: Add a default-off whole-share paper profile

**Files:** `scripts/equities_alpaca_paper_bridge.py`, its tests, a new immutable paper env/launcher.

- First add failing tests for flooring quantity, rejecting zero shares, keeping planned notional within budget, and forcing `GTC` only for an exact integer quantity.
- Add an explicit `ALPACA_WHOLE_SHARE_ONLY` policy; leave current fractional live behavior unchanged.
- Pin paper endpoint, `ALPACA_SEND_ORDERS=0`, `ALPACA_ALLOW_NEW_ENTRIES=0`, cash reserve, broker protection required, and native trailing default-off until the paper lifecycle passes.

### Task 4: Make SBR1 evidence interpretable

**Files:** preregistration, deterministic random-control module/tests, zero-risk shadow integration only after tests.

- Separate evidence universe from money universe.
- Use true UTC calendar months, deterministic hash-keyed draws, causal gate evaluation, future-hour pending state, exact cost contract, 20 controls, and a separate hash chain.
- Pin five acceptance conditions, an overturn table, and estimated date to 50 closed decisions from measured per-symbol history.
- Never submit an order or read a private endpoint.

### Task 5: Specify XAU/MT5 demo tracking

**File:** `docs/superpowers/specs/2026-08-24-xau-mt5-demo-tracker-design.md`.

- Inventory the existing demo bridge, semi-manual signal-copy path, tests, XAU data and historical results.
- Define a zero-order journal and random-control contract, token-rotation dependency, quality gates and rollback.
- Stop after the reviewable design; do not activate Bullwaves/MT5 or write order code in this cycle.

### Task 6: Preserve and hand off

- Transfer only independently verified Claude changes from the dirty tree.
- Add Polymarket as research-only backlog, not money priority.
- Update the canonical checkpoint with measured facts, caveats, expected dates and exact next gate.
- Run targeted and aggregate tests, `git diff --check`, secret-pattern review, scoped commits, and push only the clean recovery branch.
