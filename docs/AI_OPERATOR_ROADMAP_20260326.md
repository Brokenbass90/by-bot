# AI Operator Roadmap
> Last updated: 2026-03-26

## Goal
Build a safe operator layer that does more than chat:
- analyzes what the bot traded,
- analyzes market conditions,
- launches approved research,
- proposes improvements with evidence,
- and only then suggests or applies small reversible changes.

This is not a free-form autotrader. It is a supervised control plane.

## What Exists Now
- Telegram AI entrypoints already exist:
  - `/ai`
  - `/ai_results`
  - `/ai_tune`
  - `/ai_audit`
  - `/ai_code`
  - `/ai_server`
  - `/ai_regime`
  - `/ai_shadow`
  - `/ai_budget`
  - `/ai_pending`
  - `/ai_approve`
  - `/ai_reject`
- The AI already knows current project context for:
  - `breakout`
  - `midterm`
  - `flat`
  - `breakdown`
  - `alpaca`
  - `portfolio`
- Shadow journaling, approval queue, audit logging, and budget scaffolding already exist.

## Guardrails
- No direct order placement authority from AI.
- No hidden config edits.
- No live change without:
  - evidence,
  - approval,
  - rollback path.
- Every operator action must leave an audit trail.
- Research runs must use approved specs or approved templates.

## Phase Plan

### Phase 1 — Read-Only Operator
Already mostly in place.
- Read live status
- Read sleeve flags and diagnostics
- Read recent research winners
- Answer questions in Telegram
- Maintain shadow journal and budget awareness

### Phase 2 — Research Operator
Next practical step.
- Launch bounded autoresearch runs from approved templates
- Track progress and detect stalled runs
- Summarize winners and losers
- Compare fresh results against current live baseline

### Phase 3 — Strategy Analyst
Use AI where it helps most:
- detect weak sleeves by rejection mix
- compare red-month patterns and concentration risk
- suggest hypotheses:
  - tighter breadth
  - earlier exits
  - long/short split
  - symbol-pocket expansion
  - time-of-day filters

### Phase 4 — Approval-Gated Operator
Before any dangerous action:
- create proposal
- attach proof
- show rollback path
- wait for Telegram approval
- apply only small reversible changes

### Phase 5 — Controlled Auto-Research
Operator may automatically:
- restart dead research
- rotate through approved hypothesis queues
- build ranked comparison reports
- alert when a live sleeve degrades

### Phase 6 — Safe Config Steward
Only after phases 1-5 are stable.
- patch a strict allowlist of env/config keys
- snapshot old values
- write changelog entry
- support one-command rollback

### Phase 7 — Portfolio Supervisor
Future state.
- compare sleeves at portfolio level
- recommend sleeve on/off decisions
- monitor correlation and risk stacking
- coordinate crypto, Alpaca, and later Forex/CFD

## Immediate Next Tasks
1. Finish live sleeve observability so operator reasoning is based on truth.
2. Add safer entry mechanics:
   - per-symbol entry lock
   - TP/SL invariant guard
   - stale-kline protection
3. Teach operator bundles to include:
   - hypothesis
   - evidence
   - risk
   - rollback
4. Add bounded research-launch templates for:
   - `midterm`
   - `breakout side-split`
   - `Alpaca breadth/exit/concentration`
   - `TS132 pockets`
5. Later connect operator comparison views across crypto, Alpaca, and Forex.
