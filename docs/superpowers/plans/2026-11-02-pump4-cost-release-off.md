# PUMP4 closed-cost reconciliation ORDERS_OFF implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Continue the accepted TINY-2 design, not a new trading engine.

**Goal:** Complete a testable late-cost release policy, serial OFF integration and actual-account read-only VPS evidence without changing LIVE.
**Architecture:** Existing source_view/SeriesAccounting + serial supervisor. Opt-in fixed Closed PnL reconciliation policy; unapproved/unknown remains blocked. Existing authenticated GET transport only; one additional read endpoint. Read-only capture/replay uses no financial owner or original lease.
**Tech Stack:** Python Decimal, existing Bybit GET contracts, LifecycleJournal, pytest, immutable SSH staging.
**Spec:** docs/superpowers/specs/2026-10-29-pump4-tiny2-design.md and owner2Nov attached engineering authorization.

## Global Constraints

- Existing PUMP4 packet3aa49421/scope2de0b6ec/owner3669955 and Monthly unchanged; no key/GO/epoch/unit/risk change or order API.
- Work in existing dedicated codex/recovery-20260824 checkout per continuation; foreign untracked allowlist preserved. No merge into Claude or research/judge/outcome runs.
- No serial financial GO. New policy is implemented and exercised ORDERS_OFF; actual V1 lifecycle, source contract qualification and physical handoff remain separate gates.
- Fees come from complete owned executions; never twice from TRADE transactions. Funding already posted stays in known net. Matching complete closed-PnL rows provide another observed accrued net, not immutable future finality.
- Lower bound under this proposed source contract=min(known net, matched venue closed net)-observed arithmetic discrepancies-0.000001USDT per closing row. Positive pending credits are not spent. Monetary value/fee discrepancies above0.000001 per row or quantity/ownership mismatch=>UNKNOWN.
- The numeric padding is a reporting tolerance, not a universal bound on future exchange corrections. A later lower closed-cost revision beyond a previously certified envelope permanently latches new entries. Missing/unknown evidence cannot erase a certificate/latch.
- Use lower-bound risk for day/week/drawdown/lifetime. Reserve the existing1USDT next-entry scenario budget before reserving a child; not a guaranteed loss bound. Original unknown-risk custody behavior remains.
- Source policy based on Bybit closed-PnL API+P&L calculation docs (2Nov checked). Actual nonempty venue rows must be qualified before monetary approval.

## Review Focus

- Missing/partial/foreign closed rows or forged caller flags never release; quantity and fee/value reconciliation are checked.
- Late debit consumes reserve once; positive missing credit not spent; fee revisions and UNKNOWN gap cannot bypass a permanent latch.
- Same H1/plan after restart never reserves a second child; loss capacity includes pending reserve+new1risk.
- Real-account audit does not instantiate selected_owner/financial journals on LIVE or acquire original lock; real captures are not relabelled as model fills.
- Baseline defaults/no-policy behavior and no-wire carrier stay unchanged; exceptions never abandon custody.

### Task 1: Closed-cost policy and cumulative lower-bound risk
**Files:** research_lab/pump4_serial_accounting_v1.py; tests/test_pump4_serial_cost_release_v1.py.
**Interfaces:** consumes existing source_view, registry, complete /v5/position/closed-pnl pages; produces fixed COST_RELEASE_POLICY_SHA, with_cost_release(view,groups), SeriesAccounting(...,cost_policy_sha256=None), conservative summary.
- [x] Write RED cases for matched/missing/foreign/partial rows, pending debit/credit, source revisions/UNKNOWN restart and prospective risk capacity.
- [x] Implement fixed opt-in pure reducer and immutable policy binding; preserve old fields/default blockers and append-only accounting.
- [x] Run new cost tests + affected existing accounting tests; save RED/GREEN evidence; commit.

### Task 2: Existing source and serial OFF integration
**Files:** research_lab/kity_micro_transport_v1.py; research_lab/pump4_runtime_sources_v1.py; research_lab/pump4_serial_source_supervisor_v1.py; affected tests.
**Interfaces:** source.serial_closed_pnl(begin) returns exact paged closed-PnL groups; supervisor passes opt-in policy SHA, applies conservative admission and durable duplicate guard.
- [x] RED two full memory-source lifecycles with late costs/restart; no-policy remains blocked; same plan not reserved again; source failure retains custody.
- [x] Add allowlisted GET and parallel source capture, bind policy only to OFF spec. No changes to live immutable copies.
- [x] Run only affected risk/source/supervisor regressions, save evidence; commit.

### Task 3: Actual-source read-only replay and server acceptance
**Files:** scripts/run_pump4_serial_source_off_v1.py; research_lab/pump4_serial_source_supervisor_v1.py; CLI tests and reports.
**Interfaces:** explicit file-only audit mode consumes pinned raw capture/registry/policy and writes only isolated DATA output; separate pinned VPS collector uses existing bound credential loader + GET, no owner/lease. Default CLI remains NO_REQUESTS.
- [x] RED explicit mode/input pin/default side effects; live config never passed as an OFF selected owner.
- [x] Implement bounded capture/audit path in existing components; actual nonempty lifecycle requires independently proven registry, never fictitious rebind.
- [x] Stage immutable unselected candidate on VPS; network-denied affected suite/model2cycle acceptance + fresh real-account capture/audit. Report original-owner conflict as protected handoff gate, not a second writer.
- [x] One fresh Astra/high final critical review, fix important findings RED→GREEN; source/unit/lock preservation readback; publish sanitized report/checkpoint/commit. No new LIVE packet activation.

## Execution rulings

- Owner explicitly confirmed this engineering work and prior plan; native inline implementation, one final independent review. No repeated plan approval request.
- Existing accepted baseline177 is not rerun without affected code/risk. No broad repository suite: owner requests targeted checks and previous full baseline has known60 failures.
- Requested5.6 implementation model names are not in current tool catalog; primary implements; final critical Astra/high is available. No savings percentage claimed.
- Monthly actual window14:30UTC remains future at task start07:52UTC; independent postwindow check is operationalP0, no reactivation.
