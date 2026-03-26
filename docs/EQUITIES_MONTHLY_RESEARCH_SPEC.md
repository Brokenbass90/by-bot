# Equities Monthly Research Automation

## Goal

Create a repeatable monthly deep-research loop for swing equities that:
- refreshes the shortlist
- proposes entry bands
- proposes trim/exit targets
- proposes invalidation levels
- feeds a semi-automated execution layer

This is not blind "LLM picks stocks". It must be testable and operator-reviewable.

## Strategy Shape

Cadence:
- monthly research pass
- optional mid-month rebalance pass

Holding period:
- roughly 2 to 8 weeks

Output:
- ranked shortlist
- buy bands
- thesis
- invalidation
- first trim target
- final exit target

## Architecture

### 1. Data Layer

Inputs:
- price history
- recent earnings dates
- sector / market regime context
- liquidity / spread filters

Optional later:
- valuation / fundamentals
- analyst estimate revisions
- insider activity

### 2. Research Layer

Monthly job produces structured JSON:
- `runtime/equities_monthly_research/latest.json`

Schema:
- `run_ts_utc`
- `market_regime`
- `watchlist`
- `ranked_candidates`
- `rejects`

Each candidate:
- `ticker`
- `thesis`
- `entry_band_low`
- `entry_band_high`
- `stop_level`
- `trim_level_1`
- `target_level`
- `horizon_days`
- `confidence`
- `risk_bucket`

### 3. Execution Layer

Not full autonomy at first.

Mode 1:
- Telegram proposal
- operator approval
- order placement

Mode 2:
- auto-place only if candidate already approved and still inside band

## Historical Testing

Yes, this is testable, but not by naive hindsight.

Proper approximation:
- monthly rebalance snapshots
- use only data available at each month-end / month-start
- simulate entries from next session onward
- simulate exits by stop / trim / target / max-hold

This is a point-in-time proxy, not perfect reality, but good enough for first validation.

## Backtest Method

For each month:
1. freeze research universe using only data known at that date
2. rank candidates
3. keep top `N`
4. enter only inside defined entry bands
5. exit by:
- stop
- trim target
- final target
- max holding time
- thesis break / earnings blackout

Metrics:
- monthly return
- rolling return
- hit rate
- average hold time
- max drawdown
- turnover
- sector concentration

## Guardrails

- max positions
- max capital per ticker
- max sector concentration
- earnings blackout
- broad market regime filter

## Telegram Flow

Monthly message:
- `Monthly Equities Research Ready`

Body:
- top 5 candidates
- thesis summary
- target/stop bands
- current market regime

Optional commands later:
- approve
- reject
- pause ticker

## Automation Flow

Future recurring job:
- monthly research
- optional weekly monitor
- generate inbox item + Telegram summary

## Deliverables

Phase 1:
- monthly research schema
- report builder
- operator review output
- historical monthly simulation

Phase 2:
- approval workflow
- semi-automatic execution
- position monitor / target tracker
