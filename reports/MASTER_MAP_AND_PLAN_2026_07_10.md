# MASTER MAP AND PLAN 2026-07-10

This replaces the 2026-07-08 map as the current strategic starting point.

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
- Best diagnostic: `USDJPY round_level_sweep`, about `30-31` trades, `PF≈1.25-1.28`, `3/4` folds, but thin-fold preflight still fails.
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
- Continue USDJPY round-level sweep with real OOS and more instruments/time.
- Backfill real M5 if session/retest logic remains target.
- No FX capital until OOS and broker-cost gate pass.

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
