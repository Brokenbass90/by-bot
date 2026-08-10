# Next chat checkpoint — 2026-08-10

## Read first

1. `reports/CODEX_ATT1_CONTAMINATION_MAKER_AND_AUDIT_STATUS_2026_08_10.md`
2. `reports/PROJECT_MASTER_ROADMAP_2026_07_27.md` sections 19–20.1
3. this checkpoint

Do not infer live truth from AI prose. Recheck service, direct Bybit positions,
broker protection and deployed file hashes before any mutation.

## Exact current live state at handoff

- Bybit direct API: `open_position_count=0`.
- `bybot.service=active`; startup reports auth OK, `trade_on=1`, `dry_run=0`.
- Money authority: ATT1 short-only at `risk_mult=0.10`.
- BOUNCE1, IVB1 and midterm are shadow/zero-risk.
- The ADA lifecycle closed completely. ATT1 opened 180 ADA; legacy pump-fade
  DCA added 90; TP1 closed 99 and trailing stop closed 171. Broker close PnL
  `+0.73928972 USDT`, fees `0.05849218`.
- The ADA close is stored as `att1_trendline_touch__contaminated`; it must not
  enter clean ATT1 promotion statistics or ML updates.

## What is fixed and live

- Legacy DCA is confined to `pump`/`pump_fade`.
- Unexpected broker quantity growth contaminates the lifecycle and reconciles
  runner quantity/average entry.
- Clean accounting excludes contaminated closes without deleting evidence.
- Calendar expiry no longer silently disables the owner-approved tiny ATT1
  canary.

## Git versus live divergence — binding blocker

Branch `codex/dynamic-symbol-filters` is pushed through `4e3c43e`.

- `f290463` fixes misleading generic `INPLAY TP` labels so runner messages show
  the real strategy owner. It is in Git but **not live**.
- A targeted monolith deploy failed startup because the server lacks required
  local dependencies. Backup rollback restored the active flat service.
- Static import comparison found at least five missing server modules:
  `bot/att1_challenger.py`, `bot/health_truth.py`,
  `bot/portfolio_equity_guard.py`, `bot/strategy_regime_gate.py`, and
  `bot/strategy_shadow_ledger.py`.
- Do not copy the monolith again. First build an exact dependency manifest,
  stage the complete bundle outside `/root/by-bot`, run server-venv import and
  no-order startup smoke, compare hashes, verify direct flat three times, then
  deploy atomically with rollback.

## What ATT1 evidence means

ATT1 is not declared dead. The 30-day BTC/ETH maker smoke tested execution, not
the full strategy thesis:

| execution | fills/trades | net | PF |
|---|---:|---:|---:|
| current taker | 8 | `-6.14 USDT` | `0.774` |
| strict post-only | 6 fills / 11 placed | `-21.85 USDT` | `0.157` |

The only valid conclusion is that lower commission did not improve this small
window: maker selection missed favourable moves. Run the preregistered
multi-family/multi-fold maker gate before any wider verdict.

The historical backtest is not invalidated by hidden live DCA. Old live rows
are preserved but cannot scale risk. The first clean post-fix live promotion
cohort is currently N0; at the old cadence N20 may take roughly a month. Do not
replace this gate with a calendar promise.

## Research processes at handoff

Local research station is healthy `5/5`, with no order authority:

1. `research_project_audit`
2. `research_funding_frozen`
3. `alpaca_adaptive_shadow_20260726`
4. `funding_position_dynamic_shadow_20260729`
5. `xsec_v3_shadow_20260726`

Latest summaries:

- frozen funding: 9 closed, 9 fills, 0 open; N20–30 gate binds;
- dynamic funding: 51 closed, 3 open; concentration/adverse-selection audit
  still binds and capital authority is false;
- XSEC: positive aggregate dominated by outliers while median is negative;
- Alpaca adaptive: `shadow_no_orders`;
- project audit: healthy.

WIP cap is full. The preregistered strict maker grid for ATT1/BREAKDOWN/ARF1
starts at the first measurement slot; do not silently create a sixth long job.

## Alpaca gate

Alpaca remains SAFE_HOLD, not a fully autonomous strategy. The historical
fractional stop replacement failed because the broker required integer `qty`.
The August 8 repair needs its first real market-open broker acceptance receipt.
Then require broker-fill reconstruction and one exact rotation receipt before
capital expansion. Do not quote the risk-zero adaptive selector as live PnL.

## Audit and local AI

Operational reconciliation is now a first-class audit input. The non-secret
ledger `runtime/project_audit/operational_incidents.jsonl` feeds the unified
registry and Ollama fact index. Confirmed incidents include hidden ADA DCA and
the targeted-deploy dependency mismatch. Registry counts are no longer
hardcoded. Twenty focused audit/chat tests passed.

Ollama is still bounded proposal-only, not a self-proving brain. Next AI step:

1. index the complete non-secret repository by path/SHA/chunk;
2. retrieve relevant source plus current broker/event evidence per question;
3. attach provenance and freshness to every answer;
4. answer `NOT_CONFIRMED` on stale/conflicting ownership, position or runner
   state instead of guessing;
5. keep secrets, broker credentials, order submission and risk mutation out of
   local-model authority.

## Priority order for the next chat

1. Build and test atomic live dependency bundle; deploy `f290463` only after
   staged server-venv startup proof and direct-flat gate.
2. Verify the first real Alpaca fractional stop-ratchet receipt at market open.
3. Add periodic broker-position ↔ runner-owner ↔ event-ledger reconciliation,
   automatically writing mismatches to the incident ledger and fail-closing
   new adds on the affected symbol.
4. Run the preregistered maker execution gate when WIP frees; report fill rate,
   nonfill markout, adverse selection, time/symbol folds and concentration.
5. Continue ATT1 clean N without changing risk. Advance BOUNCE1 only after
   prospective decisions and exact geometry/config parity.
6. Rebuild INPLAY as a new preregistered break/retest family if its blocker
   audit shows reachable signals; do not revive the old negative family by
   relaxing filters ad hoc.

## Definition of the next real step forward

Any one of these is a real checkpoint, not prose progress:

- one clean ATT1 post-fix lifecycle with exact broker/runner/accounting parity;
- BOUNCE1 reaches its prospective decision gate without parity defects;
- frozen funding reaches N20 with no binding concentration/adverse-selection
  failure;
- Alpaca successfully ratchets a fractional broker stop and records the broker
  receipt;
- atomic live bundle deploy passes staging, direct-flat and post-start checks.

No new capital or risk follows merely from a Git commit, shadow process, raw
backtest aggregate or AI recommendation.
