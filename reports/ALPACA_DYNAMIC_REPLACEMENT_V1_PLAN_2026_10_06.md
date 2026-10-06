# ALPACA_DYNAMIC_REPLACEMENT_V1 — authorized near-term challenger

**SUPERSEDED for immediate delivery by owner October6 prospective amendment.**
Read `ALPACA_DYNAMIC_V1_DELIVERY_2026_10_06.md`, POLICY and RUNBOOK. The earlier
frozen-monthly-reserve study below remains historical/separate research, not a
November waiting gate for the new prospective version. Weekly refresh is now
in V1; forced rotation and daily refresh remain outside it.

October6 owner priority amendment: replacement V1 is the next bounded Alpaca
challenger; KITY stays highest new money priority October8–9. Read
`ALPACA_DYNAMIC_REPLACEMENT_V1_INPUT_AUDIT_2026_10_06.md`/JSON before implementation:
no verified frozen reserve in October packet; exact slot sizing/terminal authority
must be frozen. Initial stop is already entry-relative2ATR, so the separate stop
challenger must differ from baseline. No untouched holdout is yet proven.
Current intake BLOCKED_DATA_INPUT_CONTRACT; implementation/tests/holdout/PAPER
NOT_RUN. Weekly refresh stays separate and later. LIVE unchanged.

Status: **SCOPED / NOT_IMPLEMENTED / NOT_TESTED / NOT_PREREG_FROZEN**.
Owner authorized research and a roadmap task October6; current LIVE remains
frozen. This document is a concrete research work order, not a PASS verdict,
production deployment or authority to buy.

Purpose: test whether replacing vacant slots improves net capital utilization
without merely increasing turnover. Current realized live outcomes must not
choose parameters, dates, symbols or acceptance thresholds.

## Contracts to compare

- Baseline: exact current monthly selection, sizing, stop/trail, cooldown,
  portfolio limits and costs, pinned before any study run.
- Challenger A first: after a confirmed full exit and cash/finality reconciliation,
  use the next eligible name from the already frozen monthly reserve ranking.
  No same-name cooldown override, padding, same-bar look-ahead or extra slot.
  If no eligible reserve remains or the size/protection fails, retain cash.
- Challenger B separately: causal weekly candidate refresh/rotation at a fixed
  preregistered schedule. Preserve baseline risk/exit rules; count forced exits
  and their full round-trip costs. Never select an optimal weekday after results.
- More frequent refresh stays outside V1 until A/B have terminal evidence.

Equal starting capital, gross/position/concentration limits, execution timing,
fees/slippage, fractional constraints and corporate-action treatment in all arms.
Replacement only uses settled/reconciled freed sleeve capacity, not broker buying
power as permission to exceed capital. Preserve cooldown for the exited symbol.

## Bounded research sequence

1. Pin the exact baseline, candidate changes, monthly ranking/reserve artifacts,
   PIT universe/delistings, adjusted data lineage and available data coverage.
   Determine whether an untouched holdout exists; do not recycle a discovery
   period as independent confirmation. Missing PIT ranking/reserve → BLOCKED_DATA.
2. Freeze a dated preregistration before reading holdout outcomes: fixed periods,
   causal entry timing, weekly schedule, cost stress, primary net/risk acceptance
   rule, multiple-comparison handling for two challengers and sample sufficiency.
   No search over variants/timeframes; historical discovery first, untouched
   confirmation once. If no untouched history remains, forward evidence is needed.
3. Run identical event-based baseline/A/B historical replay and walk-forward.
   Report net return, max drawdown, profit factor, per-trade expectancy, turnover,
   fees/slippage, idle-cash percentage and time invested, concentration and stop/
   re-entry behavior. Define false-entry proxy in preregistration; losing trades
   alone are not causal proof of false signals. Include regime breakdown and
   sensitivity to execution gaps/fees, without changing rules to rescue an arm.
4. Unit/replay checks: no future reserve list, no held/duplicate/cooldown name,
   partial or late exit cannot free a slot, unavailable cash cannot fund a buy,
   minimum size rejection, earnings/delisting/missing-data refusal, one owner,
   native protection, partial fills, DAY expiry, restart and idempotent receipts.
5. Return READY_FOR_PAPER / KILL / BLOCKED_DATA. A positive historical result
   authorizes only an isolated PAPER shadow with explicit account isolation;
   it cannot modify existing LIVE entry/rotation flags. Preserve prospective
   signal/basket/quantity/exit/cost receipts before any promotion proposal.
6. Only after the preregistered terminal evidence and PAPER lifecycle pass,
   prepare reviewed execution/handoff/rollback and a separate owner LIVE GO.

## Existing machinery to inspect and reuse after acceptance

`scripts/equities_alpaca_paper_bridge.py` already contains
`_select_monthly_cycle_picks`, `_rotate_intended_monthly`, `replacement_picks`,
`candidate_replacement_buys` and `replacement_buys`; actual replacement buys are
conditional on `allow_new_entries`. Reuse causal ranking, finality, protection
and idempotency primitives; do not enable the generic legacy path blindly.
The current intended runner deliberately restricts entries/rotation; its exact
frozen monthly baseline must be reproduced rather than assuming every old bridge
feature is active. Software trailing is already separate from replacement.

## Priority and ownership

P0: current Alpaca DAY re-arm/accepted protection, floor/HWM and delayed fees.
ATT1: preserve original48h deadline/evidence; terminal analysis and a bounded
continuity root-cause replay before considering money. Current actual packet is
BLOCKED_DATA,9gaps/1clean; keep2–3 clean+actual dossier+ownerGO.
KITY: preserve unseenOct8 evidence and existing orders-OFF contract; no new strategy
or credential path. V1 challenger follows operational P0 and existing money gates,
starts with A and stays bounded; Claude can prepare PIT research lineage after
his current KITY commitments, without duplicate judging or production writes.
No message to Claude sent by this task.

AI may periodically summarize source-backed analytics, code/log anomalies and
possible degradation under a fixed cost cap. It cannot retune parameters, change
risk/entry gates, rewrite production or rescue a deterministic judge verdict.
