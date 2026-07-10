# CODEX HANDOFF 2026-07-10

This is the current handoff for the next Codex/Claude-style session.

## Start Here

Read these first:
1. `reports/MASTER_MAP_AND_PLAN_2026_07_10.md`
2. `reports/CODEX_FACTS_AND_PLAN_2026_07_10.md`
3. tail of `reports/PROJECT_STATE_LEDGER.md`
4. `reports/research/att1_exit_regime_ab_20260710_20260710_064618/summary.md`

Use this handoff as the operational summary. The project is a live trading system, not a notebook.

## Mission

Build a portfolio of proven money sleeves:
- Bybit crypto first.
- Alpaca equities is already live as a small canary.
- FX/CFD later, after data/cost/OOS gates.

The owner wants a long-lived electronic trader that searches, adapts, reports clearly, and improves itself. Do not approach this as "write one more strategy". Approach it as product + quant research + live ops.

Important attitude:
- Be creative in research.
- Bring new hypotheses.
- Mine open-source/market ideas if useful.
- Repair old ideas when the failure reason is clear.
- Do not treat prior FAIL as "forever dead"; treat it as evidence about what must change.
- But do not put new risk on live money without proof and owner OK.

## Live Money State At Last Check

### Bybit
- Last verified: flat, no open positions.
- Account around `1020 USDT`.
- Live-money crypto sleeve: only `ATT1 short r001` canary.
- No second crypto sleeve is live.
- Recent ATT1 live evidence:
  - BTC SL.
  - ADA manual profit, but not clean autonomous because runner/restore incident.
  - LTC SL, runner present, MFE only `0.34R`.
  - DOT SL, runner present, MFE only `0.37R`.
- Conclusion: ATT1 should not be scaled. It can remain tiny canary/telemetry while we diagnose entry quality.

### Alpaca
- Live canary around `$500`.
- Last verified equity about `$488.58`, about `-1.3%` from funded base.
- Open positions at last check had broker-side stops.
- Known issue: intraday advisory stale (`3.6d`). Fix observability/refresh before trusting intraday branch.

## What Was Actually Fixed

ADA exposed a real bug:
- runner plan could be lost after restore;
- heartbeat did not always manage every open runner position;
- web/AI could misread local stop/runner state as exchange truth.

Fixes already in project history:
- runner state persistence and restore;
- heartbeat runner manager;
- optional exchange safety TP behind `RUNNER_EXCHANGE_TP_ENABLE=0`;
- portfolio health alerting;
- web position panel warnings;
- AI context expansion.

Do not re-litigate ADA as if unfixed. Use LTC/DOT as the current signal: entries did not travel far enough to reach BE/TP.

## Fresh Research Result

ATT1 exit/regime A/B is complete:
- path: `reports/research/att1_exit_regime_ab_20260710_20260710_064618/summary.md`
- best: `small_tp1/all_regimes`, `379` trades, `+19.21R`, `PF=1.283`, `4/4` folds.
- baseline: `base/all_regimes`, `379` trades, `+18.78R`, `PF=1.277`, `4/4` folds.
- rejected: early BE, pure trail, simple trend-only filter.

Meaning:
- changing exits alone is not the answer.
- do not change live ATT1 exits yet.
- next work is entry-quality/regime meta-filtering.

## Current Candidate Board

### Crypto
- `ATT1 short r001`: live canary, not scale-ready.
- `level_memory sweep/reclaim`: real pulse, but `NO_PROMOTION`; repair with period robustness, full holdout cache, causal selector.
- `inplay maker`: near miss but FAIL; repair with entry-quality filters, not live.
- `MRB/broad pila`: FAIL; only continue if redesigned with symbol/level filters.
- `IVB1`: failed dynamic selector; can be revisited with better symbol-selection, not current money.
- `cascade real-liq`: data/research branch; needs longer stream and better trigger.
- Bull-side long sleeve remains strategically important: HZBO/breakout-retest, filtered BOS/CHoCH, support-reclaim with level memory.

### Equities
- Alpaca monthly/live canary is running.
- Need branch-level PnL clarity and stale intraday fix.
- Do not add more capital until a month of positive expectancy.

### FX/CFD
- H1 data is usable for `EURUSD,GBPUSD,USDJPY`.
- No promotion yet.
- `USDJPY round_level_sweep` is best lead.
- XAU/gold still needs better data before serious claims.

## Next Work Order

### 1. Live Health Snapshot
Before research changes:
- Check Bybit direct open positions.
- Check `runtime/live_positions.json`.
- Check `runtime/portfolio_health.json`.
- Check Alpaca account/positions/orders/stops.
- Check that AI context is current.

### 2. ATT1 Entry-Quality Meta-Filter
Build a research runner that labels ATT1 trades by MFE/MAE/outcome and tests filters around:
- regime granularity beyond simple trend/chop;
- slope steepness;
- RSI zone;
- distance from trendline/resistance;
- ATR expansion/compression;
- BTC regime;
- symbol respect/level-memory features;
- recent failed touches.

Goal: reduce LTC/DOT-style low-MFE losers while preserving the 4/4 fold baseline.

### 3. Level-Memory Repair
Complete missing holdout cache and rerun prereg with:
- full holdout;
- period robustness;
- causal symbol selection;
- long/short separated.

### 4. Alpaca Observability Fix
Fix stale intraday advisory or mark it stale/disabled in dashboard/TG. Confirm every path has broker stops.

### 5. FX USDJPY Follow-Up
Run proper OOS for `USDJPY round_level_sweep`; include cost/slippage and enough folds. No capital yet.

## Rules For The Next Chat

Research is allowed to be bold.

Allowed:
- propose new sleeves;
- rewrite bad strategies;
- use external ideas;
- add better scanners;
- run bounded research;
- create shadow/risk=0.0 candidates after validation;
- update docs/ledger;
- improve AI operator and dashboards.

Not allowed without owner OK:
- increasing live risk;
- enabling a new live-money sleeve;
- enabling `RUNNER_EXCHANGE_TP_ENABLE=1`;
- enabling `PORTFOLIO_HEALTH_AUTOCUT=1`;
- deleting old strategies blindly;
- treating tiny sample wins as proof.

The goal is momentum with proof, not pessimism.

## Current Git

Latest pushed commit at handoff creation:
- `66895e1 record att1 audit and post-pause facts`

The worktree still has many unrelated untracked historical files. Do not clean them destructively. Add only explicit files you touched.

## Owner Context

The owner is frustrated because prior sessions mixed promises, bugs, and unclear status. Keep answers factual:
- what changed;
- live-money impact;
- what is blocked;
- what is running;
- when to return.

Do not hide failures. Do not turn failures into fatalism. Convert each failure into a binding reason and next experiment.
