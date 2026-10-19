# Monthly Standing Autonomy Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans in this session; one bounded independent critical review at the end.

**Goal:** Repeated frozen Monthly cycles under one explicitly bounded standing grant, delivered ORDERS_OFF without activating financial units.
**Architecture:** Extend existing native custody and MonthlyManager. Reuse owned books, reservation IDs, accounting finalizer and notification Monitor. Keep legacy exact permits unchanged.
**Tech Stack:** Existing Python, SQLite, filesystem seals and account locks.
**Spec:** reports/ELDER_V1_2_AND_MONTHLY_AUTONOMY_2026_10_18.md, owner-provided autonomy directive and explicit instruction to continue implementation.

## Global Constraints

- No real broker requests/writes, live selection, GO fabrication or new financial permission.
- Frozen Monthly58, calendar, sizing/ratchet/cooldown and existing ceilings487.42/.70/.60/4 stay.
- NET and cancelled SHOP units, original locks and foreign allowlist unchanged.
- Existing exact GO never becomes standing GO. Expiry/revocation prevents new buys, not owned safety recovery.
- Public receipts exclude keys/private account evidence. Accounting UNKNOWN blocks new risk.

## Review Focus

- Pending accepted buy/stop from an older selection recovers before maintenance/new entry.
- Failed/reserved attempts consume the bounded session allowance across restarts/grant renewals.
- Revocation/authority/time can change after reservation; final dispatch checks again.
- Rotation creates exits after the initial finality check; each new entry still requires reconciliation.
- Source/GO/code drift, missing finality, CASH or stale captures never become an allowed buy.

### Task 1: Standing custody and entry admission

Files: research_lab/alpaca_monthly_native_binding_v1.py; tests/test_alpaca_monthly_standing_v1.py.

- [x] RED: separate fixture standing GO; same grant admits future sealed selection; exact GO rejects conversion.
- [x] Add distinct schema, exact identity/code/universe/caps, valid-from/until and revocation path.
- [x] Validate standing entry state at admission and final dispatch; count all durable attempts excluding the current reservation only in final validator.
- [x] GREEN: invalid/expired/revoked scopes prevent buy, recovery/maintenance remain callable.

### Task 2: Existing one-manager dispatcher

Files: research_lab/alpaca_monthly_cycle_v1.py; tests/test_alpaca_monthly_standing_v1.py.

- [x] RED: all-selection recovery precedes maintenance, maintenance precedes source/opening; source failure still permits owned protection.
- [x] Add a serialized tick using existing source/opening/maintain/finalize methods, immutable cost-source inbox interface and existing journals.
- [x] Preserve finality gate for every entry after rotations; emit explicit blocked/quiet/CASH states and deduplicated lifecycle notifications through existing Monitor.
- [x] GREEN: pending ticket without durable reservation never sends; no-repeat behavior survives restarts.

### Task 3: Repeated-cycle acceptance

Files: scripts/rehearse_alpaca_monthly_cycle_v1.py; tests/test_alpaca_monthly_standing_v1.py.

- [x] RED: second month actually enters using same fixture standing grant, following confirmed exit/finality of first month.
- [x] Extend existing memory-broker rehearsal; no sockets, source/selector monkeypatch or production credentials.
- [x] Test expiry/revocation, loss of buy/stop response, same-session restart, stale/CASH and missing fee finality. Demonstrate protection continues while entry is blocked.

### Task 4: Exact package, review and activation dossier

- [x] Run appropriate existing Monthly tests and exact isolated candidate import/fallback checks; no full mutating repository suite.
- [x] One bounded astra/high review; verify actual runtime model/effort, fix and regress material findings.
- [x]19Oct owner explicitly approved code-only upload after prior auto-review rejection. Exact44 package348690be staged UNSELECTED; independent server hashes/43AST PASS,77protectedpins/lock/NET/SHOP preserved. Full server runtime/financial activation not implied. See reports/MONTHLY_STAGING_AND_BRAIN_CONTEXT_2026_10_19.md.
- [x] Publish receipts, remaining real producer/accounting/activation dependencies, canonical board and commits. Owner approval is the final financial step after a concrete reviewable packet, not an implementation permission question.


## Acceptance / next gate

165 exact PASS,34 candidate imports,0 fallback.93 targeted overlap. Review R1–R3
fixed/regressed; root also fixed marker leaf maintenance. Runtime astra/high verified.
Actual automatic broker-cost producer and production applying wrapper are NOT
implemented here: next bounded engineering work; no financial activation claimed.
VPS read-only77pins/lock813893/NET/SHOP states verified. Full suite not run.
