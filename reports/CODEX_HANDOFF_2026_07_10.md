# CODEX HANDOFF 2026-07-10

This is the current handoff for the next Codex/Claude-style session.

## Start Here

Read these first:
1. `reports/PROJECT_SYSTEM_AND_ROADMAP_2026_07_10.md`
2. `reports/PROJECT_CANONICAL_INDEX_2026_07_10.json`
3. `reports/MASTER_MAP_AND_PLAN_2026_07_10.md`
4. tail of `reports/PROJECT_STATE_LEDGER.md`
5. current `git status` and latest direct runtime/server snapshot

Use this handoff as the operational summary. The project is a live trading system, not a notebook.

Do not repeat a completed audit just because a new chat started. Compare `last_session` and `next_actions` in the canonical index, verify freshness, then continue the first unfinished action. At session end update the index and append the ledger.

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
- `USDJPY big-figure sweep short-only` is the best lead; the current round-step is 10 JPY, not normal 00/50 FX levels.
- Local native trend/retest wiring has been repaired. First H1 smoke produced trades but no promotable edge.
- XAU/gold still needs better data before serious claims.

### Truth/Control Fixes Awaiting Deploy

- Weekly AI forensics now distinguishes forensic-cache gaps, mixed accounting and clean cohorts.
- AI full-context direct import is fixed.
- Alpaca v1 close reconciliation NameError is fixed.
- Alpaca v3 shadow launcher is executable.
- Fake web trading controls/SIGHUP are blocked until effective ACK exists.
- FX level metadata/current-price bug and unbounded prefix work are fixed.

All are local only until reviewed commit + flat-window deploy. They did not change orders or risk.

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
Run a frozen short-only prereg for the big-figure sweep; separately define/test 00/50 levels. Include chronological OOS, costs, sessions/news and enough folds. No capital yet.

## Time Expectations

- One to two sessions: finish review/commit/deploy package and server manifest.
- Three to seven days: operational normalization plus first strict ATT1/FX/crypto verdicts.
- Two to four weeks: shadow candidates only if gates pass.
- Six to twelve weeks: first meaningful clean live/shadow portfolio assessment.
- Do not promise stable income by date or compensate for time pressure with leverage.

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

Latest pushed commits:
- `07b0bdd fix: preserve web auth and freeze Alpaca live churn`
- `0e7eb73 research: repair level memory and validate ATT1 entries`
- `23f9446 fix: harden Alpaca accounting and research gates`

The worktree still has many unrelated untracked historical files. Do not clean them destructively. Add only explicit files you touched.

## Owner Context

The owner is frustrated because prior sessions mixed promises, bugs, and unclear status. Keep answers factual:
- what changed;
- live-money impact;
- what is blocked;
- what is running;
- when to return.

Do not hide failures. Do not turn failures into fatalism. Convert each failure into a binding reason and next experiment.

## Evening checkpoint — continue from here

- Web `Unauthorized` is fixed on VPS: auth config restored, service active, one user visible, `/ping` healthy. Normal web deploy now preserves instance auth state.
- Alpaca real account is intentionally `safe-hold`: no new entries, no stale/daily/midmonth rotation, existing positions remain protected by broker stops. Daily refresh cron is commented with a backup. Do not re-enable until monthly-vs-daily exact-live parity verdict.
- Alpaca historical intraday v1 equity/PnL log is `DATA_INVALID` due repeated booking after a crash. Idempotent atomic broker-fill ledger is implemented and tested locally, but must not be deployed until the corrupted baseline is backed up/rebuilt from broker fills.
- ATT1 exact full rerun rejected the simple slope+RSI filter: `3/4` folds, PF `1.327`, WR `57.7%`, lower net/frequency versus base `4/4`, PF `1.277`, WR `57.9%`. Keep current live params/risk unchanged. Next ATT1 experiment needs richer entry cards (R2, pivots, touch distance, ATR state, level respect, BTC context) and/or causal universe expansion.
- Repaired level-memory strict result: short resistance sweep/fade passed temporal OOS and a strong unseen-symbol holdout, but failed stressed costs (PF `1.003`) and concentration (top symbol `38%` versus `<35%`). Final `NO_PROMOTION`; do not run M5/shadow until the binding weaknesses are repaired. Long support reclaim and Elder variants failed.
- Alpaca research had another parity mismatch: the refresh simulator was hard-coded `top_n=3` while live advertised four positions. Fixed A/B reproduced top3 `+53.28%`/PF `7.326` and top4 `+50.75%`/PF `6.744`, so the old top4 headline is reproducible. Local data ended `2026-04-27`; fresh May-June OOS remains blocked on an isolated data refresh. The VPS newer report is top3, not exact live-cardinality parity.
- ATT1 richer entry-card cohort completed. On newer windows through Jul 10, base is weaker (`346` trades, PF `1.205`, WR `56.3%`, 3/4). Exact `R² >= 0.80` rerun improved to `264` trades, PF `1.285`, WR `57.6%`, 4/4, net `+13.41` versus base `+12.98`, with lower drawdown. Higher-cost stress failed (`263` trades, PF `1.078`, 1/4; latest fold negative). No live/shadow change. Next test is measured live costs plus maker/retest execution and a fresh holdout, not another threshold grid.
- VPS research queues are temporarily disabled because the active liquidity-sweep run exactly duplicated a completed 486-row zero-PASS grid. Backups exist next to both configs. Re-enable only after queue fingerprint/resume repair and obsolete-task cleanup.
- Full fast tests: `897 passed`.
