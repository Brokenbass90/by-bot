# Trading Station — canonical project map

Updated: 2026-08-31.

Canonical workspace: `bybit-bot-recovery-20260824`.

Current handoff: `reports/CODEX_SESSION_CHECKPOINT_2026_08_31.md`.

## Product objective

Build a multi-market station in which strategy research, live execution and
capital control share one reproducible contract. The system may adapt by
proposing and testing changes, but no model or research job can grant itself
money authority.

## End-to-end lifecycle

```text
idea intake
  -> preregistration
  -> causal replay
  -> random/matched control
  -> costs, stress, concentration and PIT checks
  -> zero-risk shadow
  -> broker paper lifecycle
  -> tiny canary
  -> allocator + regime governor
  -> degradation monitor
  -> scale, reduce or disable through a new receipt
```

## Layer map

| Layer | Main locations | Contract |
|---|---|---|
| Money runtime | `smart_pump_reversal_bot.py`, `bot/` | Orders only through explicit live authority |
| Strategy logic | `strategies/` | Pure signal/event geometry where possible |
| Research/live parity | `research_lab/live_native_*`, `research_lab/adapter_parity.py` | Same decision, fill, exit and cost semantics |
| Research factory | `research_lab/`, `backtest/`, `configs/research/` | Frozen inputs, prereg, controls and receipts |
| Canonical station | `research_lab/canonical_station.py`, `scripts/canonical_station_migration.py` | One evidence epoch, exact process parity, fail-closed migration |
| Regime/router/allocator | `scripts/build_regime_state.py`, `scripts/build_symbol_router.py`, `scripts/build_portfolio_allocator.py` | Enable/reduce/disable sleeves; no silent risk increase |
| Broker integrations | Alpaca/Bybit/MT5 adapters and deploy scripts | Broker truth overrides UI and Markdown |
| Observability | `web/`, Telegram, `runtime/`, `reports/receipts/` | Explain state; never invent money truth |
| AI analysis | Ollama/DeepSeek/Codex proposal paths | Secret-free and proposal-only |

## Market sleeves

### Crypto

- ATT1 current frozen configuration: OOS `FAIL_CLOSED`; not eligible for risk
  expansion.
- SBR1 current frozen configuration: `INCONCLUSIVE_LOW_N` and negative; no
  money integration.
- Bull Continuation V1: approved implementation plan, research-only.
- XSEC PIT V5: approved plan, currently blocked on delisted-contract history.
- Order blocks, imbalances, horizontal/sloped levels and pattern atlas are
  feature/research infrastructure, not independent money authority.

### Alpaca

- Protective management is a separate contour from entry selection.
- New entries remain gated by PIT selector, stress, SHA reconciliation and a
  complete paper lifecycle.
- Any current live statement requires a fresh broker/service read.

### XAU/Forex

- XAU unchanged-replication plan exists.
- Use shared controls, causal data, costs and demo/paper lifecycle before MT5
  authority.

### Future lanes

- Polymarket, DeFi and cross-exchange arbitrage remain idea/backlog lanes until
  data provenance, execution costs, operational/legal constraints and controls
  are explicit.

## Truth hierarchy

For a live claim, reconcile all four layers:

1. Git source SHA and release bundle;
2. deployed file hashes and deploy receipt;
3. service, heartbeat and effective authority;
4. direct broker positions, orders, fills and accounting.

Conflicts are labelled `NOT_CONFIRMED`. Research, shadow, paper and UI state do
not override broker truth.

## Canonical migration state

Task 5 is commit `482a536`. It can stop only an exact legacy screen after a
fresh actual canonical launch, independently replayed process-kind comparator,
current evidence hashes, exact authorization scope and immediate OS identity
recheck. The completed dry-run is `NOT_CONFIRMED`; no screen was stopped.

Canonical Station Task 6 still needs to connect this gate to status/audit and
write the operator runbook. It must not perform a live migration.

## Current execution queue

```text
XSEC shared controls (first shared dependency)
  +-- XSEC PIT V5 preflight and delisted-data blocker
  +-- Bull frozen contract
  +-- XAU unchanged replication controls

Bull event detector + execution model (parallel, no shared-file conflict)

Canonical Station Task 6 (parallel, research infrastructure only)

Dirty-tree preservation (isolated groups, never blind staging)
```

## Repository boundary

- Canonical integration: `bybit-bot-recovery-20260824`.
- Legacy/active evidence source: `bybit-bot-clean-v28`.
- Do not patch both trees in parallel.
- Do not commit `_snimki/`, `_to_delete/`, `*.bak*`, env files, sessions, logs
  or bulk raw/generated data.
- Move unique legacy work by explicit file list, secret scan, tests, review and
  one scoped commit at a time.

## Non-negotiable gates

- No reuse of consumed ATT1/SBR1 OOS v1.
- No current-137 substitution for XSEC closed-contract PIT.
- No money/risk/slot change from a research finding alone.
- No legacy stop from a dry-run or self-declared PASS.
- No AI authority to trade, promote or restore risk.
