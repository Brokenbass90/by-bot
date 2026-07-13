# MASTER MAP AND PLAN 2026-07-10

> **2026-07-13 canonical override:** read `reports/RECOVERY_CHECKPOINT_2026_07_13.md`,
> `reports/PROJECT_CANONICAL_INDEX_2026_07_13.json` and
> `reports/NEXT_CHAT_START_PROMPT_2026_07_13.md`. They supersede live/research
> status below. Strict pump verdict is `NO_PROMOTION`; FX/Alpaca remain blocked.
>
> Latest recovery truth: `reports/PROJECT_RECOVERY_TRUTH_AND_ROADMAP_2026_07_11.md`.
> Latest continuation prompt: `reports/NEXT_CHAT_START_PROMPT_2026_07_11.md`.
> The July 11 recovery report supersedes stale live/deploy counts below.
>
> Canonical continuation point: `reports/PROJECT_SYSTEM_AND_ROADMAP_2026_07_10.md`.
> Machine-readable index: `reports/PROJECT_CANONICAL_INDEX_2026_07_10.json`.
> This document remains the concise strategic summary; the canonical roadmap resolves conflicts and contains the session/timeline protocol.

This replaces the 2026-07-08 map as the current strategic starting point.

## Morning Update — 2026-07-11

Read first: `reports/MORNING_RECOVERY_CHECKPOINT_2026_07_11.md`.

- FX/CFD V2 causal research frame and three new families were committed and pushed as `376ad21` before outcomes were viewed.
- Full prereg: all six long/short sleeves are `NO_PROMOTION`; base PF is already below 1, so this is not merely cost drag. No FX/CFD demo/live capital.
- Strict FX data has `0/6` promotion-valid symbols. Four pairs are diagnostic-only after partial-H1 removal and market-gap segmentation; `EURJPY/XAUUSD` remain data-blocked.
- Clean independent InPlay short is `NO_PROMOTION` (stress PF `1.075`, only two symbols traded, concentration `67.7%`). Old InPlay is frozen; build event-first long expansion and short pump-exhaustion successors.
- Alpaca remains safe-hold: equity `$486.93`, positions `ABBV,ABNB,GE,SCHW`, stops `4/4`. Safety improved; profitability has not been proven improved.
- Latest Jul 11 implementation checkpoint: `e286534`; documentation commits follow it. VPS remains `f7ed011` and was 22 implementation commits behind. Resolve current HEAD; code is pushed, not deployed to live.

Next order: rebuild Alpaca fill ledger baseline; verify ATT1 expiry/effective env; refresh/calibrate FX data; then implement one-causal-change V3 repairs. Do not rerun the failed V2 parameter set or enable a new money sleeve.

## Crisis-Recovery Update

- The TG AI `missing_candles` diagnosis was wrong: it measured post-hoc forensic cache gaps, not missing live candles or broken exits. ATT1 had zero such gaps in that report.
- ATT1 current r001 has only four clean-start closes. Three autonomous closes lost; ADA's manual profit contaminates the net. This is a serious warning but not enough data to declare the strategy dead.
- Simple `trend_only` and early-BE repairs already lost to the all-regimes baseline in strict A/B. Do not patch live from the last few stops.
- There are multiple level engines and a renderer, but no mandatory canonical level contract across research/live/web. Consolidation and parity are now explicit roadmap work.
- FX native trend/retest wiring had a real structural defect; it is fixed locally and now produces honest diagnostic trades. No repaired row is capital-ready.
- Web trading mutations are blocked fail-closed until a live consumer writes an effective-state acknowledgement. The old overlay is proposal history, not live control.
- Read-only VPS drift manifest found 877 records but only two tracked generated configs. A hidden fail-open base risk was removed locally: approved baseline now caps ATT1 short at 0.10 and sets every other sleeve risk to zero.
- Local P0 fixes are not deployed. Live risk/orders were not changed.

## Product Vision

Build a long-lived electronic trader, not a one-strategy bot.

The target system trades multiple markets and survives regime changes by combining:
- live money sleeves with strict risk rails;
- a research factory that continuously searches, repairs, and retires edges;
- regime/risk routing so the bot knows when a sleeve is favored, degraded, or disabled;
- AI operator context for status, explanations, triage, and owner-approved actions;
- observability so the owner understands what is live, what is shadow, what is research, and what needs a decision.

The working principle stays: search wide, run narrow. New ideas are welcome. Only live capital is gated.

## Current Live Money Truth

### Bybit Crypto
- Account around `1020 USDT`.
- Last verified state: Bybit flat; no open positions at the check.
- Live-money crypto sleeve: only `ATT1 short r001` at canary risk.
- No second crypto sleeve is live.
- ATT1 recent clean-window facts:
  - `BTCUSDT Sell`: SL `-0.4942`.
  - `ADAUSDT Sell`: manual profit `+1.3645`, but not a clean autonomous win due runner/restore incident.
  - `LTCUSDT Sell`: SL `-0.3983`; runner existed, MFE only about `0.34R`.
  - `DOTUSDT Sell`: SL `-0.4598`; runner existed, MFE only about `0.37R`.
- Interpretation: ADA was an execution continuity bug and has been fixed. LTC/DOT are entry/regime/exit-threshold problems, not the same bug.

### Alpaca Equities
- Live canary capital: about `$500`.
- Last verified snapshot: equity about `$488.58`, drawdown about `-1.3%` from funded base.
- Positions at that check: `ABBV`, `GE`, `PANW`, `SCHW`.
- Broker-side stop orders existed for all open positions.
- Known gap: `Alpaca Intraday` advisory was stale (`3.6d`). Treat that as observability/refresh debt before trusting intraday behavior.

## What Was Fixed Recently

- Runner state is now persisted and restored for live positions.
- Heartbeat runner management calls exits for every open runner-enabled trade, not only symbols actively flowing through detect/tape paths.
- Startup/status Telegram output separates enabled strategy code from actual live-money sleeves.
- Portfolio health monitor writes `runtime/portfolio_health.json`; alert-only by default.
- Position web view and AI context expose runner warnings, exchange stop truth, and Alpaca position visibility.
- Daily/AI context path was expanded, but stale Alpaca intraday refresh still needs attention.

## Research Verdicts

### ATT1 Exit/Regime A/B
Result path: `reports/research/att1_exit_regime_ab_20260710_20260710_064618/summary.md`.

Best:
- `small_tp1/all_regimes`: `379` trades, `+19.21R`, `PF=1.283`, `WR=57.9%`, `4/4` positive folds.

Baseline:
- `base/all_regimes`: `379` trades, `+18.78R`, `PF=1.277`, `WR=57.9%`, `4/4` positive folds.

Rejected for live change:
- `trend_only` filter: `2/4` folds.
- early BE `0.5R`: `3/4`, lower net.
- early BE `0.3R`: weak.
- pure trailing: too few trades, `2/4` folds.

Verdict: do not change ATT1 live exits based on this. The next useful work is entry-quality/regime meta-filtering and post-fix live telemetry.

### Crypto Candidates
- Level-memory sweep/reclaim: real pulse, but strict prereg `NO_PROMOTION`.
  - Base `83` trades, `+11.8122R`, `PF=1.2998`.
  - Stress weak: `PF=1.1086`.
  - Time folds only `2/4`.
  - OOS selector failed; holdout cache thin/missing.
  - Next: redesign for period robustness, complete holdout cache, then rerun prereg.
- Inplay maker: near miss, not promotion.
  - Best strict maker fill row: stress `PF=1.173` vs prereg `>=1.2`, only `2/4` folds.
  - Fill-rate was acceptable; edge stability was not.
  - Next: repair entry-quality with level memory / regime / symbol selection, not direct shadow.
- Broad MRB / naive "pila": failed.
  - `PF≈0.84`, `0/4` folds.
  - Do not rerun the same broad z-score basket without causal symbol/level filters.
- IVB1 dynamic selector: failed.
- Cascade real-liquidation branch: zero-trade diagnostics improved; needs longer 60-90d liquidation/OI stream and better trigger conditions.

### FX/CFD
- H1 coverage is usable for `EURUSD`, `GBPUSD`, `USDJPY`.
- Full H1 grid produced no promotion row.
- Best historical diagnostic: `USDJPY round_level_sweep`, about `30-31` trades, `PF≈1.25-1.28`, `3/4` folds, but thin-fold preflight still fails. It is actually a big-figure/decade-handle detector under the current step formula, not ordinary FX 00/50 levels.
- Side split of the fixed `RR=2.5 / SL=1 ATR` row: short `18` trades, `+10.6487R`, `PF=1.946`; long `12`, `-4.6731R`, `PF=0.587`. Only the short hypothesis deserves a new prereg.
- Repaired H1 smoke: USDJPY trend pullback `40` trades, `-0.284R`, `PF=0.990`, `2/4` folds. This proves plumbing/frequency, not edge.
- `EURUSD` rows are too small; session/range fade is negative on USDJPY.
- `XAUUSD` remains data-quality/backfill dependent before serious verdicts.

Verdict: no FX/CFD money yet. USDJPY round-level sweep is the best research lead.

## Strategy Coverage Roadmap

The goal is not to delete old families. The goal is to organize them and make each earn its place.

Priority families:
1. ATT1 short family: keep canary; improve entry-quality/meta-filter before scaling.
2. Level-memory range/sweep/reclaim: primary path for "pila", false breakout, and quality-level bounce.
3. HZBO / breakout-retest long: still important bull-side branch, needs clean prereg.
4. Filtered BOS/CHoCH: structure-break branch, needs implementation/validation.
5. OI/funding/carry: potential DD-smoother, requires history and cost model.
6. USDJPY round-level sweep: first FX follow-up.
7. Alpaca monthly/intraday: keep small live canary; fix stale intraday observability.

Long/short symmetry is desired, but not by naive mirroring. Each side needs its own params, symbols, OOS, stops, and breaker.

## AI Operator And Control Plane

The onboard AI should see:
- open positions and exchange stop truth;
- realized/unrealized PnL in USD;
- sleeve health;
- latest research verdicts;
- git rev / deploy state;
- errors/log tails;
- Alpaca account/positions/orders.

AI can propose, diagnose, and prepare trade cards. Owner approval remains required for new live money behavior. `ai_manual_v1` is a separate controlled path with token, mandatory SL, expiry, and tiny risk.

## Development Operating Model

Every idea must end in one of:
- `LIVE_CANARY`
- `SHADOW`
- `REPAIR`
- `DATA_BLOCKED`
- `NO_GO`

Every failed run must state the binding reason:
- `entry_quality`
- `exit_model`
- `regime_mismatch`
- `cost_drag`
- `data_quality`
- `sample_too_small`
- `execution_parity`

Exploration can be creative and fast:
- new setups;
- external ideas;
- new symbols;
- new filters;
- new market branches;
- soft scans.

Promotion to money stays strict:
1. Exploration pulse.
2. Preregistered validation with fixed params.
3. Stress and cost checks.
4. Time folds.
5. Symbol/OOS or causal selector.
6. Shadow/risk=0.0.
7. Tiny canary with breaker and expiry.
8. Scale only after clean live expectancy.

## Next Best Work

### P0: Live Truth First
- Check Bybit open positions and ATT1 counters.
- Check Alpaca account, positions, stops, stale intraday advisory.
- Confirm `runtime/portfolio_health.json` and AI context are current.

### P0: ATT1 Meta-Filter Research
Use the post-fix live losses as diagnostic labels.

Research questions:
- Which features separate ADA-style move from LTC/DOT false starts?
- Does bear/bull/chop regime improve entry quality if modeled more finely than simple `trend_only`?
- Are slope steepness, RSI, distance-to-level, recent ATR expansion, symbol respect, and BTC regime useful?
- Can we cut low-MFE losers without killing the 4/4 fold base edge?

No live risk change until this produces a strict result.

### P1: Level-Memory Repair
- Complete missing holdout cache: `INJ,TIA,OP,RUNE` and any required mid-caps.
- Add period robustness requirement.
- Rerun sweep/reclaim with causal symbol selection.
- If PASS: wire to shadow/risk=0.0 only.

### P1: Alpaca Observability
- Fix stale intraday advisory or explicitly mark it disabled/stale in UI/TG.
- Verify every entry path attaches broker-side stop protection.
- Produce clear PnL-by-branch: monthly vs intraday vs closed sells.

### P1: FX Follow-Up
- Freeze and test USDJPY big-figure sweep short-only with real chronological OOS and cost/session/news splits.
- Test instrument-aware 00/50 levels as a separate hypothesis.
- Repaired trend/retest branches stay diagnostic until side-specific strict gates pass.
- Backfill real M5 if session/retest logic remains target.
- No FX capital until OOS and broker-cost gate pass.

## Planning Time Ranges

- `1-2 sessions`: canonical memory, local P0 review, reviewed deploy diff and server inventory.
- `3-7 days`: flat-window VPS normalization, Alpaca cron/fill verification, ATT1 entry cards, first strict FX/crypto verdicts.
- `1-2 weeks`: canonical level contract/parity and side-specific repair gates.
- `2-4 weeks`: at most one crypto and one FX/equity candidate reach shadow, only if PASS.
- `6-12 weeks`: enough clean live/shadow evidence for a scale/pause/replace decision.
- Stable income has no honest calendar promise; it depends on verified edge, live costs, capital and drawdown tolerance.

### P2: New Idea Mining
Encouraged:
- better long/bull crypto sleeves;
- support/reclaim with level memory;
- breakout-retest;
- structure break with false-break filter;
- orderflow/liquidation/funding features;
- smarter dynamic symbol selection;
- external open-source idea mining.

Discouraged only for live money:
- martingale/grid without bounded risk;
- broad unfiltered mean reversion;
- tiny-N promotion;
- loosening gates after seeing results.

## Current Risk Recommendation

- Do not raise Bybit risk today.
- Do not add money to Alpaca today.
- Do not promote a new crypto sleeve today.
- Do keep research aggressive.
- Do keep ATT1 as a canary/telemetry source unless owner explicitly pauses it.

## Evening execution update — 2026-07-10

1. `Web`: recovered. VPS auth state had been overwritten with zero users. Restored and protected against normal deploy overwrite.
2. `Alpaca LIVE`: moved to safe-hold. The previous implementation was daily rotation, not monthly research parity; it realized about `-$5.72` over 7 closes. Existing positions remain broker-stop protected, but new entries/rotation are off pending exact-live replay.
3. `ATT1`: current base remains the live research champion. A simple descending-slope + RSI 50..70 filter improved PF slightly but failed one fold, did not improve WR in the exact rerun and cut frequency/net. No live parameter change.
4. `Crypto candidate`: repaired horizontal resistance sweep/fade, `short-only`, Elder off, produced an exploration pulse (`42` trades, PF `1.20`, 3/4). Strict follow-up passed temporal OOS and unseen symbols but failed stressed PF (`1.003`) and concentration (`38%` from the top symbol versus `<35%`). Verdict `NO_PROMOTION`; long support reclaim and Elder variants also failed.
5. `Inplay/pump fade`: retain the concept, especially for mania/bear unwind, but do not rerun the old maker grid. Its latest stress gate was close but failed (`PF=1.173`, 2/4). Rebuild it as event-first expansion/exhaustion with level memory and side/regime-specific gates after the current resistance-sweep validation.
6. `Alpaca research parity`: the refresh simulator was hard-coded to three names while the live config advertised four. Cardinality is now explicit. Same-window A/B reproduced top3 `+53.28%`/PF `7.326` and top4 `+50.75%`/PF `6.744`; the latter matches the old published headline. Local data ended `2026-04-27`, so fresh May-June evidence is still missing. The isolated refresh runner is ready but external data access was blocked by the current tool quota.
7. `Alpaca ledger`: an atomic, idempotent broker-fill ledger is complete locally and full tests pass. Deploy only after reconstructing the old false `+$442` baseline.
8. `ATT1 next wave`: newer four-fold base weakened to PF `1.205`, WR `56.3%`, 3/4. Exact `R² >= 0.80` challenger improved PF to `1.285`, WR to `57.6%`, 4/4 and slightly raised net while cutting frequency about 24%. Adverse cost stress failed at PF `1.078`, 1/4. No promotion. Next is actual-cost measurement and maker/retest execution, then a fresh holdout; frequency should later come from causal universe expansion, not lower-quality entries.
9. `Git`: safety, accounting and research repairs committed through `23f9446`; full suite `897 passed`.

Immediate order:
- diagnose level-memory short cost sensitivity and concentration without reopening a broad grid; do not advance to M5/shadow yet;
- rebuild Alpaca v1 ledger from broker fills and add idempotent execution IDs;
- finish Alpaca top3/top4 parity pulse, then exact monthly-vs-accidental-daily-vs-adaptive replay;
- then return to inplay pump expansion/fade and ATT1 richer entry-card/universe work.
