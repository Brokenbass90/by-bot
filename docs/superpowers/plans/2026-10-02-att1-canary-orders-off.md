# ATT1 canary orders-OFF implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. Preserve the native execution method of the September 8 migration plan; use one bounded critical review before delivery.

**Goal:** finish the existing NEW ATT1 execution preparation with explicit cash limits, exclusive ownership and recovery evidence, while every NEW order command remains inert.

**Architecture:** reuse the existing bybot process, SQLite ATT1 reservation, source-bound lifecycle journal, frozen coordinator and broker transport. Add a thin preparation boundary that translates coordinator intents into captured commands; it cannot submit them. Public observation remains an independent, unchanged evidence stream.

**Tech Stack:** Python, SQLite FULL-synchronous transactions, Fraction/decimal-text accounting, existing Bybit GET-only collectors and pytest.

**Spec:** `docs/superpowers/plans/2026-09-08-att1-profile-migration.md`, `reports/ATT1_MICRO_CANARY_RECONCILIATION_2026_09_08.md`, and the owner's October 2 instruction: pause OLD new entries after fresh flat/no-orders plus postcheck; prepare NEW fixed-USDT canary orders-OFF; retain 2–3 clean prospective filled terminals; regime work is separate.

## Global Constraints

- Frozen base profile: `79d23e38a6bb851fb7e300c2e0d0c22b48b671585d4c060eb5384c192b128050`. Strategy, admission, freshness, 2s threshold, coordinator decisions and journal authority remain unchanged. Original stop, target rebasing, BE/trailing OFF and 336h exit remain fixed.
- Separately hash the execution binding. Public risk=1/notional=100 and OLD multiplier0.10 are not an absolute money-risk authorization.
- Fixed initial-stop risk `R` in USDT must not exceed a fresh, source-proven OLD budget; it cannot grow with equity. Exact `R` is a private numeric proposal until owner approval. Missing effective sizing inputs produce `BLOCKED_RISK_INPUTS`, never a guessed amount.
- UTC daily admission budget `D = 2 × R`: include OLD+NEW ATT1 losses, execution fees, funding debits and outstanding risk/cost reserves. Restart, route switch, profits and retry do not reset expenditure. Unknown costs block admission; this is not a guaranteed bound on realized loss after gaps.
- One account-wide occupied ATT1 slot, including pending, partial, unknown, protected and exit states. Notional at most100USDT and bounded further by fresh broker/venue limits and `R`. Floor quantity, reject below minimum quantity/notional; no fallback. Rounding cannot exceed `R`.
- Initial money admission symbols: ADA/BTC/DOT/ETH/LINK/LTC/SOL/SUI USDT. Frozen Fixed51 signal generation remains intact.
- Every NEW command remains orders-OFF. No POST client, executable activation flag, second credentialed daemon, production DB migration or deployment to the OLD service in this preparation cycle.
- Preserve Alpaca LIVE, active OLD management/SL/TP, the applied OLD entry pause, public epochs/journals, sealed evidence and foreign diff. Never automatically resume OLD.
- Money activation separately requires 2–3 clean prospective filled terminals with terminal net-R, source/target parity, fresh absolute-risk comparison and exclusive handoff, then explicit owner GO. Clean execution evidence alone does not prove positive strategy edge.

## Review Focus

- OLD and NEW daily costs must share complete coverage; missing historical OLD identity or UTC-boundary coverage blocks preparation rather than treating it as zero. Task1 tests this.
- Daily cash/risk checks, reservation and finality spend-transfer must be atomic across competing SQLite connections; a crash cannot release a slot before its realized debits are persisted. Task2 tests this.
- A late OLD fill after a flat GET returns handoff to draining; flat endpoints alone cannot prove all old intents final. Task2 tests this.
- Captured protection commands and broker ACKs are not protection evidence; only accepted protection covering actual filled remainder permits a protected state. Task3 tests this.
- A complete archive with numeric caps must still be incapable of sending after a config edit; no single flag turns this preparation into LIVE. Task4 tests this.

## Delivery — October2

Tasks1–4 implemented in the existing tree. Engineering242 local/233 target tests
PASS plus historical14-session/162-record receipt oracle. One critical review
returned two P1 findings, fixed and regression-verified in3f999c9; no repeat review
was claimed. Actual numeric binding/cost/drain/watermarks remain BLOCKED, public
clean cohort0 at18:55UTC, owner GO false. See ATT1_CANARY_ORDERS_OFF_READINESS_2026_10_02.json
and HANDOFF runbook. Task checkmarks denote delivered engineering, not money
authority or an authenticated BUILD_READY receipt.

## Original implementation map (pre-build history)

- Done: `bot/att1_coordinator_adapter.py` durable route/decision/one-slot reservation; authenticated entry, native-stop, exit, cash/funding and finality recovery. `SEND_ENABLED=False`; NEW has no send API.
- Done: `research_lab/att1_lifecycle_profile.py::bind_broker_replay_profile(base, binding)` separately binds risk/notional/daily caps, max1 and sendfalse; `admit_signal(...)` floors quantity and rejects venue minimum violations.
- Missing: cumulative daily admission enforcement, complete OLD budget provenance, production bridge to frozen NEW intents, explicit captured-command fault acceptance and a dedicated inert canary package.
- `scripts/package_att1_lifecycle.py` packages public simulation only. Do not extend or deploy it as a money runner. September task checkboxes are historical; inspect current functions/tests rather than reimplementing them.
- OLD pause applied October2 15:36:43UTC. This is an operator new-entry control, not `pause_att1_route` or a completed financial handoff. It is not instantaneous drain and its existing malformed/missing-file behavior is fail-open. The NEW boundary must additionally require valid pause/drain evidence.

## File responsibilities

- Create `bot/att1_canary_preparation.py`: strict private evidence/budget projection and inert command preparation; no transport method that submits orders.
- Modify `bot/att1_coordinator_adapter.py`: additive preparation-only budget provenance in the existing reservation tables and atomic reservation enforcement; no new authority/ledger/core.
- Modify `smart_pump_reversal_bot.py`: default-disabled lazy preparation seam using the selected existing account/process; no NEW call reaches its live submit/protection/exit functions.
- Create `scripts/package_att1_canary_orders_off.py`: allowlisted source closure, numeric binding validation, offline acceptance manifest and rollback/handoff dossier.
- Tests: `tests/test_att1_canary_budget.py`, `tests/test_att1_canary_preparation.py`, `tests/test_package_att1_canary_orders_off.py`; extend existing exclusive-reservation tests only where their interface changes.
- Receipt: `reports/ATT1_CANARY_ORDERS_OFF_READINESS_2026_10_02.json`; runbook: `reports/ATT1_CANARY_ORDERS_OFF_HANDOFF_2026_10_02.md`. Dates identify this plan's cycle; later observations retain their real timestamps.

### Task 1: Source-proven fixed cash limits and daily projection

**Files:** create `bot/att1_canary_preparation.py` and `tests/test_att1_canary_budget.py`. Reuse profile binding and L3 cash accounting without modifying their frozen synthetic behavior.

**Interfaces:**
- `validate_canary_budget_inputs(binding: Mapping, old_budget_evidence: Mapping, cash_evidence: Mapping, *, now_ms: int) -> dict`: canonical validated budget inputs or `AdapterViolation`; never returns authority.
- `project_att1_daily_budget(validated: Mapping, occupied: list[Mapping], *, proposed_risk_usdt: str, proposed_cost_reserve_usdt: str) -> dict`: returns `admitted: bool`, stable `reason`, UTC day, decimal-text spent/reserved/remaining amounts and provenance hash.
- Inputs use the existing broker binding fields. Additional evidence binds selected account fingerprint, deployed sizing source/config hashes, raw authenticated source hashes, effective equity, effective risk/volatility/breaker inputs, fee tier, complete OLD+NEW cash coverage and actual receipt timestamps. Reuse the existing60s authenticated-identity age limit; all collection pages must bind to that same account/client. These declarations alone do not establish authenticity.
- Daily cash events require stable source identity, account, OLD/NEW ATT1 attribution, economic timestamp, signed gross realized PnL, execution fees and signed funding cash with coverage interval. Use validated journal/GET receipts; do not derive costs from breaker net PnL or charge both broker net PnL and its included fees.
- Debit policy: sum realized losses, fees and funding debits once; positive realized PnL/funding does not replenish the spent budget. An occupied reservation contributes its full unreleased risk plus conservative source-bound costs. Carry occupied reserves over midnight; late events invalidate earlier incomplete coverage and are charged to their economic day. Unknown/mismatched coverage blocks further admission.
- Proposed reserves must derive from the exact admitted quantity, rounded stop/price, execution-binding hash and captured command hash. Cost reserve conservatively covers their source-bound entry/exit fees and funding assumption; absent coverage blocks preparation. Reject understated or cross-binding caller values. These reserves do not guarantee the eventual market loss.

- [x] **Step1 — write RED tests:** `test_missing_old_cash_coverage_blocks`, `test_duplicate_or_net_plus_fee_cash_cannot_double_count`, `test_profit_does_not_refill_daily_budget`, `test_midnight_carries_occupied_risk`, `test_late_cost_invalidates_incomplete_coverage`, `test_stale_or_changed_account_and_sizing_inputs_block`, `test_fixed_risk_does_not_grow_with_equity`. Toy assertions: `R="0.50"`, `D="1.00"`; spent`0.30` + existing reserve`0.60` + proposal`0.20` is rejected. Toy numbers are never deployed owner caps.
- [x] **Step2 — run RED:** `.venv/bin/python -m pytest tests/test_att1_canary_budget.py -q`; expect missing new interfaces, not a preexisting unrelated failure.
- [x] **Step3 — implement the two interfaces:** exact arithmetic and deterministic source hashes; budget is conservative and monotonic within a UTC day. Numeric OLD reference must reproduce the deployed sizing calculation with every effective input; missing dynamic input stays blocked. Preserve a private numeric proposal and public redacted receipt separately.
- [x] **Step4 — run GREEN:** new budget tests plus `tests/test_att1_broker_replay_binding.py` and `tests/test_att1_broker_cash_accounting.py`; all pass, original synthetic profile bytes unchanged.
- [x] **Step5 — commit only Task1 files** after `git diff --cached --check`.

### Task 2: Atomic cash-aware reservation and proven handoff

**Files:** modify `bot/att1_coordinator_adapter.py`; extend `tests/test_att1_exclusive_reservation.py` and new budget tests. Only temporary test databases are migrated.

**Interfaces:**
- Extend existing `att1_decisions` additively with nullable decimal-text `risk_reserve_usdt`, `cost_reserve_usdt`, UTC-date text `budget_day_utc`, and TEXT hashes `budget_evidence_sha256`, `execution_binding_sha256`, `command_sha256`; NULL occupied reserves mean unknown and block NEW admission. Preserve existing decision PK and unique occupied-slot index.
- Extend existing `att1_route` with preparation provenance `budget_day_utc` (TEXT), `spent_debits_usdt` (decimal TEXT), `cash_coverage_sha256` (TEXT), `cash_finality_frontier_ms` (INTEGER); monotonic spent debit projection is derived from immutable evidence, not a second cash authority. Same-day changed/incomplete coverage cannot reduce spent; rollover never releases occupied reserves. Frontier advances only with authenticated complete terminal evidence; later budget coverage must include the finalized source identities, not merely have a newer timestamp.
- Add `reserve_new_att1_preparation(con, account: str, *, symbol: str, side: str, h1_close_ms: int, now_ms: int, validated_budget: Mapping, proposed_risk_usdt: str, proposed_cost_reserve_usdt: str) -> dict`. It returns existing stable reservation identity plus bound budget provenance; no send authorization.
- Preserve existing call compatibility for `reserve_att1_decision`, `pause_att1_route` and `prepare_att1_cutover`. Extend `finalize_att1_reservation` with optional keyword `validated_budget: Mapping | None = None`: budget-bound NEW reservations cannot finalize without authenticated complete terminal cash coverage and matching lifecycle/command provenance. Legacy unbudgeted callers keep their existing behavior. Thread this optional evidence through the existing adapter finality/reconciliation functions used by Task3; none may bypass the guarded finalizer.
- Factor private transaction-local reservation/finality logic: no nested transaction, early commit or budget check outside `BEGIN IMMEDIATE`. For a budget-bound terminal, transfer its actual losses/fees/funding into the durable day projection and release the occupied slot in the same transaction. Store a finality coverage frontier in route provenance; an older cash snapshot cannot admit a new reservation even after a zero-loss terminal. Replay conflicts/missing coverage block release.
- Reuse `prepare_att1_cutover` with complete late-fill/finality receipts and imported per-symbol OLD H1/cooldown/terminal watermarks. C remains an H1 close strictly after fresh drain, last OLD H1 and preparation time. Missing old intent inventory/watermarks blocks readiness; never invent them from wall clock.

- [x] **Step1 — write RED tests:** `test_budget_and_slot_checked_in_one_transaction`, `test_missing_reserve_migration_blocks_new`, `test_two_connections_cannot_spend_same_budget`, `test_restart_and_route_switch_do_not_refill`, `test_unknown_order_and_late_old_fill_keep_handoff_draining`, `test_pre_c_signal_and_old_cooldown_are_preserved`, `test_release_crash_then_stale_cash_retry_blocks`, `test_bound_finality_cannot_bypass_spend_transfer`, `test_reserve_matches_admitted_command_and_binding`.
- [x] **Step2 — run RED:** `.venv/bin/python -m pytest tests/test_att1_exclusive_reservation.py tests/test_att1_canary_budget.py -q`; new assertions fail before implementing the additive interface.
- [x] **Step3 — implement atomic reservation and finality:** under one FULL-synchronous SQLite write transaction validate route/account/evidence/cash projection, read all occupied reserves, enforce budget, persist reservation/provenance/watermarks and commit. Guarded finality transfers terminal cash debits before freeing the slot within its own single transaction. Replay/source hashes reconcile the DB projection after a crash; conflict is blocked. Historical spend is retained.
- [x] **Step4 — run GREEN:** those tests plus authenticated entry/finality/native-stop tests. Kill/reopen synthetic test subprocesses at before/after reservation commit; no second decision, fresh link ID, TTL release or OLD auto-resume.
- [x] **Step5 — commit only Task2 files** after staged diff verification.

### Task 3: Frozen coordinator to captured commands, including recovery

**Files:** extend `bot/att1_canary_preparation.py`; add lazy disabled seam beside existing ATT1 dispatch in `smart_pump_reversal_bot.py`; create `tests/test_att1_canary_preparation.py`. Reuse `LifecycleSession` and existing adapter GET collectors/recovery functions.

**Interfaces:**
- `prepare_new_att1_entry(con, account: str, *, profile: Mapping, intent: Mapping, validated_budget: Mapping, now_ms: int) -> dict`: use existing `admit_signal`, Task2 reservation and stable link identity; returns captured command/provenance with `orders_allowed=False`.
- `prepare_new_att1_management(*, session: LifecycleSession, coordinator_intent: Mapping, binding: Mapping, now_ms: int) -> dict`: translate existing protection/exit intent into captured venue payload and causal identity; decisions remain the existing coordinator's.
- `validate_canary_handoff(*, pause_snapshot: Mapping, broker_snapshot: Mapping, old_intent_inventory: Mapping, old_watermarks: Mapping, now_ms: int) -> dict`: requires valid current OLD pause, fully reconciled old intents, flat/no orders, source-bound last H1/cooldown and same account. Result is preparation readiness, not actual route activation.
- Preparation seam is absent/defaultOFF. It uses the existing selected account and off-thread GET work; public unit and credential scope remain unchanged. Captured command output has no `.send()`/POST callback. `SEND_ENABLED` remains literalFalse and invalid true activation input is rejected. The existing live OLD branch is still governed by its actual pause and otherwise keeps its behavior; NEW error cannot fall back to OLD entry.

- [x] **Step1 — write RED tests:** same OLD+NEW signal/concurrent symbols; crash before hypothetical send; possible-send/ACK-loss recovery uses same link ID and GET lookup; duplicate fill/restart unknown order; missing/wrong-qty protection; partial TP1/final dust; delayed funding/fee mismatch; risk/stop rounding above cap; below-minimum qty/notional; understated/cross-binding reserve; management during paused/occupied/budget-blocked/incident state. Assert incomplete costs give null net-R, reserve stays occupied and no synthetic protection ACK/fill is generated. Mock live submit/SL/exit methods to raise on any call; command preparation must never call them, including when enabled inputs are supplied.
- [x] **Step2 — run RED:** `.venv/bin/python -m pytest tests/test_att1_canary_preparation.py -q`; new interface failures expected.
- [x] **Step3 — implement only the inert seam:** derive/bind risk and cost reserves to the exact admitted command; persist intent before exposing command. Consume real source-bound evidence through existing recovery functions and guarded budget finality. Recheck pause/drain/route/budget gates for entry only. Owned protection/reconciliation/reduce-only exits remain preparable during occupied, paused, budget-blocked and incident states; validate their account/ownership/remainder without requiring flat or replenished admission budget. Native protection payloads cover filled residual quantity; captured payload or HTTP ACK alone cannot set protected state. Partial exits remain reduce-only and quantity-bounded.
- [x] **Step4 — run GREEN:** new tests and existing coordinator/profile, exclusive reservation, broker binding, authenticated transport/entry/finality, native-stop, cash-accounting and operator-control suites. Verify historical public receipts byte-for-byte with the deployed pins; bind any new broker preparation journal to its own execution implementation hash. Run target Python in a disposable directory with no production state or network mutations. Target failure is explicit blocked acceptance.
- [x] **Step5 — commit only Task3 files** after staged diff verification and one bounded critical financial review.

### Task 4: Inert source closure, readiness receipt and rollback/handoff

**Files:** create `scripts/package_att1_canary_orders_off.py`, `tests/test_package_att1_canary_orders_off.py` and the receipt/runbook above. Leave the public packager unchanged.

**Interface:** `build(out: Path, *, binding_path: Path, acceptance_path: Path) -> dict`. Pure local packaging; validate numeric binding/source acceptance, collect an explicit allowlist/transitive import closure, emit archive and per-file SHA256 manifest. No SSH, env discovery, service invocation or deployment.

- [x] **Step1 — write RED tests:** reject missing/non-numeric caps, incomplete acceptance/provenance, stale comparison, sendtrue/financial authority, missing dependency and source mismatch; exclude `.env`, private raw broker/account/credential records, foreign files and unrelated repository content. Config edits cannot create a callable send path. Repeated same inputs produce identical archives.
- [x] **Step2 — run RED:** `.venv/bin/python -m pytest tests/test_package_att1_canary_orders_off.py -q`.
- [x] **Step3 — implement package and dossier:** private numeric execution binding is a separate mode0600 artifact; public archive binds its hash/redacted limits. Include exact source commit/file closure, commands-only entry/protection/exits, target acceptance, existing GET-only recovery, budget/handoff rules and explicit outstanding activation prerequisites. Rollback before activation retains OLD pause and management; rollback after any future real fill closes NEW admission while the same NEW protection/reconciliation remains alive. Never resume OLD over unknown/NEW exposure.
- [x] **Step4 — run GREEN:** packaging tests and a disposable extraction/import/self-check in local and target Python. Receipt states `BUILD_READY_ORDERS_OFF` only if every build test/source/target requirement passes. Independently record `clean_filled_terminals`, `money_gate_met`, `owner_go=false`, `orders_allowed=false`; unmet public cohort does not prevent building, but missing risk/cost/target acceptance prevents BUILD_READY. No archive is installed on the money service in this task.
- [x] **Step5 — commit explicit plan/implementation/receipt/runbook paths**, verify remote HEAD, preserve foreign SHA, update MASTER/NEW_CHAT/TOP with actual results and the next unmet gate. No broad strategy tests or sealed-window consumption.

## Execution handoff and parallel work

Plan self-review: all owner requirements map to Tasks1–4; the five review-focus cases have owning tests. This plan prepares an inert execution package. Autonomous money dispatch and owner activation remain a separately reviewed financial step; a ready build cannot be advertised as installed LIVE.

Bounded critical review (`gpt-6-astra/high`, verified runtime turn_context) identified three material gaps, now addressed: atomic terminal spend-transfer before slot release; reserves bound to admitted quantity/payload; admission gates apply only to entry and cannot block protection/exits. This is a written-plan review, not implementation acceptance or a new test PASS.

Tasks1–4 are now implemented; next measurable cycle is bounded actual-account risk/cost/handoff input collection, while public terminals accumulate. Preserve native execution, with a fresh bounded critical review at the financial integration boundary.

- Public NEW: prospective collection continues; first October2 C98 session is a simulated IOC nonfill and does not count toward 2–3 clean filled terminals. No arbitrary activation date.
- Alpaca: October2 DAY re-arm PASS retains its original broker timestamp. Observe current manager; next broker-backed regular-open transition October5 13:30UTC/16:30Cyprus, subject to fresh broker calendar. No Alpaca change in this plan.
- BullWaves FX: owner/Claude obtain read-only actual `BullWaves-LIVE` account/server/type and all7-pair spread, commission, swap/triple-rollover/slippage inputs. Frozen cost judge may return acceptable costs, reject or insufficient data; a current export alone cannot prove summer+winter coverage or net edge. No broker orders or automatic financial promotion.
- Claude: PM2 valid v5 frozen judge and TOLPA_1D prospective. ETS2M frozen verdict no earlier October10 19:00UTC. Do not duplicate/merge research blindly.
- Regime/Elder: separate prospective audit/design; no policy change in this plan or blockage of canary engineering. Factory work follows existing lead verdicts and dependency-safe inventory; increasing entry count is not an acceptance metric without net expectancy after costs.

Implementation rulings: management binding carries reservation_account to verify
UID-bound stable exit IDs; handoff inputs attach to the validated budget. Full
intent/command persists in the existing decision row. Budget-bound finalizer also
requires lifecycle_session and exact cash component source identities; historical
command cash is explicit and excluded from current-day expenditure. The archive
excludes the runnable money monolith, retaining only its inert AST seam/hash.
One whole-boundary critical review followed code packaging; primary fixed and
verified its two findings, without a second broad audit. Global57 baseline test
failures are preserved/reported rather than expanding into sealed research.
