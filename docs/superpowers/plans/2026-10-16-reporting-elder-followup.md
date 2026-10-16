# Reporting V1 and Elder HEDGE_V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Native/root-only execution; do not retry or replace exhausted independent reviewers.

**Goal:** Connect journal-backed reporting independently of trading, and prepare the frozen Elder hedge shadow adapter.

**Architecture:** Reporting observes durable execution records in a separate process; render/send failures cannot enter a writer's critical path. Keep old web/bybot inhibition intact and expose only authenticated read/report routes from a separate profile. Elder consumes the first causal ETS2S record and frozen context, never a closed-outcome signal or a new strategy generator.

**Tech Stack:** Python, existing matplotlib renderers, existing FastAPI/auth/photo sender, immutable JSON exports and read-only SQLite.

**Spec:** `research_lab/otchety/TRADING_OS_REPORTING_V1.md`; research commit a82d2a6, `research_lab/KONTRAKTY_DLYA_CODEX_2026_10_15.md` §2b. Original sources/hashes are in UPSTREAM_SOURCE.json and reports/evidence/elder_hedge_preparation_20261016/source_manifest.json.

## Global Constraints

- KITY latency policy98ae…8f3ee is spent: no retry/reset/new policy/deadline change or monetary action.
- No Alpaca/Bybit writer, risk, signal, research judge, C1–C3, outcome-consumption or source-contract change.
- UI/reporting money is copied from authoritative journal fields; UNKNOWN stays unknown, with separate currencies/modes and no double counting.
- Any new reporting profile lacks Bybit account credentials, order routes or legacy watchdog restart authority.
- Elder standalone is KILL; implement only HEDGE_V1 shadow under frozen §2b, including UNKNOWN regime admission. No invented money budget.

## Review Focus

- Process/HTTP timeout after Telegram send: retain a durable delivery-unknown claim; do not blindly duplicate.
- Partial fill/protection without final accounting: show actual quantities and UNKNOWN money, never false flat or zero fees.
- Writer updates a SQLite/source during reading: use a read transaction and source identity; do not mutate working journals.
- Web startup imports credential loaders or mutators: refuse that profile; old service remains inhibited.
- Elder source first seen after outcome / incomplete H1 waiting window: keep causal pending/UNKNOWN, never validate from future R.

### Task 1: Preserve actual KITY result and first report

**Files:** reports/evidence/kity_critical_path_20261016; research_lab/otchety.

- [x] Independently verify executions, cash, full stops and flat; retain terminal receipt and spent authority.
- [x] Import frozen Reporting modules by Git ref and retain upstream hashes.
- [x] Run upstream reporting tests (3 PASS), render and visually inspect the actual card.
- [x] Send ONE card via existing photo sender, retain response hash/message ID. Not continuous reporting.

### Task 2: Continuous journal export, reporting and read-only web

**Files to create:** research_lab/trading_os_report_sources_v1.py, research_lab/trading_os_reporting_v1.py, web/reporting_routes.py, web/reporting_readonly.py, tests/test_trading_os_reporting_v1.py.
**Existing files:** web/activity_feed.py; web/routes/data_routes.py for an additive Alpaca provider only.
**Interfaces:** source readers return ReportEvent v1 plus source_ref/source_sha256; delivery consumes one immutable event ID; web reads the same export/card IDs.

- [ ] Add failing tests: duplicate event ID, unavailable source, nonterminal fees UNKNOWN, currency/mode separation, source correction as superseding event, renderer failure fallback, unknown-send no repeat, read-only HTTP route table.
- [ ] Implement stable journal-event IDs, source-bound immutable exports, delivery claims, timeout-isolated card rendering/text fallback and bounded health state.
- [ ] Add Russian feed labels/evidence IDs, authenticated card/timeline/portfolio routes and GET-only Alpaca candles with existing candle schema. Retain Bybit behavior.
- [ ] Exercise real saved payloads and browser flows; no live trade writes. Portfolio must declare coverage when journal fields are missing.
- [ ] Install separate reporting profile with only needed report/auth/data credentials; verify old web/bybot inhibitors, KITY owner, Alpaca and unknown-send barriers unchanged.
- [ ] Verify one actual event reaches Telegram and web from the same immutable export; enable source-backed daily summary only with durable day claim. Do not claim CONNECTED before these checks.

### Task 3: Elder hedge shadow adapter

**Files to create:** research_lab/elder_hedge_shadow_adapter_v1.py; tests/test_elder_hedge_shadow_adapter_v1.py.
**Interfaces:** compile_intent(first_signal, frozen_context, instrument, sourced_budget); consume_closed_h1(intent, bars, asof); immutable opportunity/execution-intent export from §1.

- [x] Pin §2b, HEDGE research evidence and external yadro/vnutri/strategy files without changing Claude or reading new cohort outcomes.
- [ ] Test BULL refusal/UNKNOWN admission; short ref×1.002, stop×4, six closed H1 bars, pending vs expired semantics, lot/tick sizing, caller budget≤1/3 portfolio, one symbol, duplicates/restart and causal timestamps.
- [ ] Implement against exact pinned yadro.ispolnenie semantics with CONTROL targets; source hashes and input-only fields required, no R-derived choices.
- [ ] Forced restart proof; collect P1–P5 prospective parity as events, with no calendar waiting added and no synthetic tests counted toward30 events.
- [ ] Return shadow/static readiness or one exhaustive material blocker list. No monetary sender or research/900 judge invocation.
