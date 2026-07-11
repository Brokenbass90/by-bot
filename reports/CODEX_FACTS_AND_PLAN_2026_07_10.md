# CODEX FACTS AND PLAN 2026-07-10

## Superseding facts — 2026-07-11 morning

Canonical detail: `reports/MORNING_RECOVERY_CHECKPOINT_2026_07_11.md`.

- Alpaca safe-hold snapshot: equity `$486.93`, cash/BP `$328.45`, `ABBV,ABNB,GE,SCHW`, broker stops `4/4`; no entries/closes after safe-hold, only protective stop re-arm. This is safer operation, not an improved edge claim.
- Clean InPlay short independent additivity: stress `N=42`, `+1.4389R`, PF `1.075`, only ETH/AVAX traded, concentration `67.7%` -> `NO_PROMOTION`.
- FX/CFD V2 prereg from pushed `376ad21`: all six candidate sides negative in base and stress -> `NO_PROMOTION`. Best whole-family stress PF is `0.747`; no FX money.
- FX strict data: zero promotion-valid symbols; four diagnostic-only pairs after complete-H1/gap/censor controls; EURJPY and XAUUSD blocked.
- Local/origin `376ad21`; VPS `f7ed011`, `15` commits behind. No research/live deploy, order or risk change.
- Next hypotheses are V3 event/confirmation redesigns, not parameter relaxation: failed-break retest short, flat horizontal range rejection, and frozen range-edge expansion retest.

## Live Truth

### Bybit
- VPS `/root/by-bot`: commit `f7ed011`, `bybot.service=active`.
- Direct Bybit REST at check: `open_position_count=0`; local live mirror: `count=0`, `dry_run=false`, `trade_on=true`.
- Live-money crypto sleeve is still only `ATT1 short r001` at canary risk. No second crypto sleeve is live.

### ATT1 Clean-Window Trades Since `ATT1_EDGE_START_TS=1783162792`
| UTC close | Symbol | Result | PnL USD | Notes |
|---|---|---:|---:|---|
| 2026-07-05 21:55 | BTCUSDT Sell | SL | -0.4942 | Pre-runner visibility fix era |
| 2026-07-07 13:13 | ADAUSDT Sell | manual/profit | +1.3645 | Profitable entry, but autonomous exit incident; do not count as clean win |
| 2026-07-09 05:11 | LTCUSDT Sell | SL | -0.3983 | Runner present; MFE only `0.34R`; no TP/BE trigger |
| 2026-07-10 01:49 | DOTUSDT Sell | SL | -0.4598 | Runner present; MFE only `0.37R`; no TP/BE trigger |

Clean-window net is roughly flat in USD (`+0.0121`), but this is misleading because the only positive row was manual and preceded by an execution incident. Autonomous post-fix ATT1 behavior is currently two consecutive SLs.

### What This Means
- The ADA issue was an execution/restore/heartbeat bug; that path has been fixed.
- LTC/DOT are different: runner state exists, but price never reached `R=1`, so breakeven/trailing did not arm. This is an edge/regime/exit-threshold problem, not the same runner bug.
- ATT1 should not be scaled. Treat it as data-collection canary until a strict exit/regime audit passes.

### Alpaca
- Live snapshot at `2026-07-10 06:20 UTC`: equity `$488.58`, cash/BP `$246.21`, account active, not blocked.
- Approx drawdown from funded base `$494.90`: about `-1.3%`.
- Positions:
  - `ABBV`: `-$3.94` (`-4.69%`)
  - `GE`: `-$0.01`
  - `PANW`: `+$3.43` (`+5.56%`)
  - `SCHW`: `+$0.01`
- Broker-side stop orders exist for all open positions: `ABBV`, `GE`, `PANW`, `SCHW`.
- `Alpaca Intraday` advisory is stale (`3.6d`). That is an observability/refresh issue to fix before trusting the intraday branch.

## Research Verdicts

### Level-Memory Sweep/Reclaim
- Strict prereg result: `NO_PROMOTION`.
- Best base row: `83` trades, `+11.8122R`, `PF=1.2998`, `WR=56.6%`.
- Stress weak: `+4.6026R`, `PF=1.1086`.
- Time folds weak: `2/4` positive; early folds negative (`-5.2R`, `-4.17R`), later folds positive.
- OOS selector failed: `37` windows, `75` test trades, `+15.9227R`, only `14` positive windows, `pass=false`.
- Holdout blocked/thin: only `APT,ARB,NEAR,SEI` present; missing/no cache `INJ,TIA,OP,RUNE`; holdout does not pass.

Verdict: real pulse, but not robust. Do not shadow/live. Next step is redesign for period robustness and full holdout cache.

### FX/CFD
- H1 data coverage is fixed for `EURUSD,GBPUSD,USDJPY`.
- Full H1 grid completed: no promotion row.
- Best diagnostic branch is `round_level_sweep`, especially `USDJPY`:
  - `USDJPY round_level_sweep rr=2.5 sl=1.0`: `30` trades, `+5.976R`, `PF=1.265`, `3/4` folds, but `preflight_go=false` due thin fold.
  - `EURUSD` best rows have only `3` trades; not usable.
  - `session_range_fade` is broadly negative on USDJPY (`PF<0.75`).
- Trend/session-retail logic on current files is not proven because some "M5" paths are effectively H1 and session/retest setups need real intraday granularity.

Verdict: no FX/CFD money. `USDJPY round_level_sweep` is the first FX follow-up candidate, not a live sleeve.

### Other Crypto Candidates
- Broad MRB / naive "pila": FAIL (`PF≈0.84`, `0/4` folds).
- Inplay maker: near miss but FAIL (`PF=1.173` vs prereg `>=1.2`, `2/4` folds).
- IVB1 dynamic selector: FAIL.
- Cascade real-liq: zero trades; diagnostics point to OI/direction/liquidity rarity and short data window. Needs 60-90d stream.

## Failure Analysis

1. **Execution bugs existed and were real.**
   - ADA exposed runner restore/visibility/heartbeat failure.
   - Fixes added: runner state persistence, heartbeat runner manager, position exit truth, portfolio health.
2. **Current losses are not the same bug.**
   - LTC/DOT had runner state.
   - They failed before reaching BE/TP. That means entry/regime/exit threshold needs research.
3. **Backtest/research plumbing has had real defects.**
   - FX coverage was misread because H1 files were treated like different granularity.
   - Cascade had zero-trade diagnostics missing until added.
   - Therefore every promotion must include data-quality and execution-parity checks.
4. **Do not infer "strategy works then breaks" from first few live trades.**
   - Current samples are tiny and can be selection-biased.
   - But the clean live evidence is not good enough to scale. The correct response is stricter gating, not risk increase.

## Development Operating Model

### One Page Of Truth
Use this report plus `PROJECT_STATE_LEDGER.md` as the current state. New sessions should read:
1. `reports/CODEX_FACTS_AND_PLAN_2026_07_10.md`
2. tail of `reports/PROJECT_STATE_LEDGER.md`
3. latest handoff, if newer than this file

### Do Not Repeat Loops
Every strategy idea must end in one of five states:
- `LIVE_CANARY`
- `SHADOW`
- `REPAIR`
- `DATA_BLOCKED`
- `NO_GO`

Every FAIL must state the binding reason:
- `entry_quality`
- `exit_model`
- `regime_mismatch`
- `cost_drag`
- `data_quality`
- `sample_too_small`
- `execution_parity`

### Promotion Ladder
Exploration can be soft. Money cannot.
1. Exploration: find pulse.
2. Prereg validation: fixed params, stress, folds, concentration, OOS.
3. Shadow/risk=0.0: live telemetry only.
4. Tiny canary: only after clean shadow and owner OK.
5. Scale: only after multiple weeks, positive live expectancy, and no execution incidents.

## Next Engineering Actions

### P0: ATT1 Audit Before More Confidence
- Run strict ATT1 exit/regime A/B:
  - base runner
  - pure trail
  - small TP1
  - early BE at `0.3R/0.5R`
  - regime filter: allow only confirmed trend vs include chop
- Required outputs: per-regime PF, MFE capture, stop-then-reverse rate, gave-back-profit rate, fold robustness.
- No live scale until this passes.
- Implementation started: `scripts/run_att1_exit_regime_ab_20260710.py`.
  - It reads the actual live `configs/att1_short_r001_canary_20260702.env` geometry and changes only the exit/regime variables.
  - Important harness lesson: early smoke attempts produced false zero-trade outcomes when the runner was not using the live r001 env/cache path. The script now forces `data_cache` and the live r001 env so this specific testing error is not repeated.
  - Short control run on one 180d fold showed the harness is live and sees trades. One-window result is not a verdict: `base/all_regimes` had `210` trades, `PF=1.270`, while `base/trend_only` had `172` trades, `PF=1.185`; early BE `0.5R` did not cleanly dominate.
  - Full 4-fold A/B completed: `reports/research/att1_exit_regime_ab_20260710_20260710_064618/summary.md`.
  - Best row was `small_tp1/all_regimes`: `379` trades, `+19.21R`, `PF=1.283`, `WR=57.9%`, `4/4` positive folds. Baseline `base/all_regimes` is almost identical: `379` trades, `+18.78R`, `PF=1.277`, `WR=57.9%`, `4/4` positive folds.
  - Rejected for now: `trend_only` filters (`2/4` folds), early breakeven at `0.5R` (`3/4`, lower net), early breakeven at `0.3R` (weak), and `pure_trail` (too few trades, `2/4` folds).
  - Verdict: exit-only tinkering does not explain the live LTC/DOT losses. Do not change live ATT1 exits or raise risk based on this run. The next useful ATT1 work is entry-quality/regime meta-filtering plus live/post-fix telemetry, not a quick breakeven patch.

### P1: Alpaca Visibility And Guard Rails
- Fix stale intraday advisory path or explicitly disable intraday reporting until fresh.
- Confirm monthly v38 stop lifecycle: stop present after every rebalance, stale stops cancelled, new stops attached.
- Keep `$500` canary; no extra funds until a month of positive expectancy.

### P1: FX Follow-Up
- Focus on `USDJPY round_level_sweep` with real OOS and more instruments/time.
- Do not run FX capital until a preflight row passes and real broker cost/slippage model is included.
- Backfill real M5 if session/retest logic remains a target.

### P2: Level-Memory Redesign
- Complete missing holdout cache: `INJ,TIA,OP,RUNE`.
- Add period-robust filters: avoid strategies whose edge appears only in late folds.
- Re-test as separate prereg, not by loosening the failed gate.

## Current Risk Recommendation
- Do not increase Bybit risk.
- Do not promote new crypto sleeve today.
- Consider reducing ATT1 to observation-only or keeping only minimal canary until the ATT1 audit completes. If kept live, treat every trade as telemetry, not expected income.
