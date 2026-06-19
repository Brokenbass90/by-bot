# CODEX handoff — 2026-06-19

This is the canonical continuation point after the 2026-06-15..19 sessions.
Read this file first, then `PROJECT_MAP.md`, then the linked evidence. Older
handoffs remain historical context and contain statements corrected by later
live/server verification.

## 1. Repository and safety

- Workspace: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28`
- Branch: `codex/dynamic-symbol-filters`
- Latest pushed commit at handoff: `7e5296d`
- Full local suite: `401 passed` on 2026-06-19.
- Worktree is intentionally dirty with user/Claude artifacts. Never use
  `git add .`; stage only files owned by the current change.
- `configs/web_config.json` contains authentication/TOTP material and must not
  be committed.
- Restart `bybot.service` only after private Bybit API confirms zero positions
  repeatedly. Use `scripts/restart_bybot_when_flat.py`.

## 2. Verified live state

Server state at `2026-06-19 13:56 UTC`:

- `bybot.service`: active after a three-confirmation flat restart.
- Bybit equity: about `121.09 USDT`.
- `trade_on=true`, `dry_run=false`, `open_trades=0`, regime `bear_chop`.
- Live is not globally frozen. Allocator status `disabled` is not a hard block;
  `hard_block` is the blocking field.
- Effective risk-bearing sleeves: `flat_resistance_fade=0.30x` and legacy
  `range=0.25x`.
- Scan/shadow at zero risk: ATT1, bounce1, breakdown, IVB1, midterm.
- Disabled: Elder v2, ASB1 slope-break, HZBO1.

Current live Range is `sr_range_strategy.RangeStrategy`, not
`strategies/alt_range_scalp_v1.py` (ARS1). Treat them as different
implementations until a deliberate migration is made.

## 3. Live performance evidence

Complete available mixed journal through 2026-06-18:

- 40 closes, net `-3.81 USDT`, PF `0.517`, WR `32.5%`.
- Current live Range: 14 closes, net `-0.2542`, PF `0.885`, WR `35.7%`.
- Range long: 11 trades, net `-0.7842`, PF `0.617`.
- Range short: 3 trades, net `+0.5301`, PF `4.364`; sample is too small for a
  profitability claim.
- `flat_resistance_fade`: 2/2, `+0.3234`; also too small for a claim.

`missing_candles` in old `trade_forensics` output means the offline report could
not find matching history in its cache. It does not prove that live entered or
managed positions without candles. The exact Range reconstruction on 2026-06-18
successfully joined fills to one-minute candles.

Primary artifacts:

- `reports/LIVE_TRADING_AUDIT_2026_06_18.md`
- `reports/RANGE_FORENSICS_AND_ADAPTIVE_PAPER_2026_06_18.md`
- `reports/trade_forensics/trade_forensics_20260618_175502_range_exact_v3_20260618.md`
- `reports/audit_bundle_20260619/AUDITOR_README.md`

## 4. Deployed engineering fixes

- `586e037`: promotion backtests use next-bar-open fills.
- `f03a8cf`: InPlay v3 timeframe parity, closed bars and look-ahead fix.
- `890e429`: preserve interrupted research evidence.
- `bb504c0`: VWAP research requires next-open validation.
- `88d8d1a`: live Range direction is gated by market regime.
- `d035dbb`: snapshot separates effective runtime from configured env.
- `ea17a90`: targeted ARS1 regime-fragility research.
- `2029f50`: Pump-fade research keys and time-based cooldown repaired.
- `7e5296d`: persistent unsupported-symbol quarantine and IVB next-open spec.

Range regime-side behavior:

- bear permits a configured short;
- bull blocks a short;
- bull does not automatically enable unvalidated legacy Range long;
- neutral/unknown retains static approved side configuration.

Maker-first entry has timeout, confirmed cancel, safe market fallback and
post-fill risk-expansion checks. `CLUSDT` exposed an extra failure: Bybit exposed
the instrument but rejected account order entry. Unsupported instruments are now
persisted for 30 days in `runtime/unsupported_symbols.json`, excluded from
trading, excluded from breaker failures, and reported without raw API internals.
`CLUSDT` was seeded into quarantine before restart.

## 5. Strategy research results

All results include configured fees/slippage. Live promotion also requires
next-open execution and monthly/OOS stability.

### ARS1 — range scalp candidate

- Local next-open r004: 108 trades, `+16.61%`, PF `1.682`, DD `6.68%`.
- Monthly stability failed because October and November were red.
- Direction split was positive over the full window: long PF `1.619`, short PF
  `1.791`; both sides lost in October.
- Server limited r004: `+13.72`, PF `1.555`, DD `6.93`; this does not override
  the monthly failure.
- Targeted 64-combination regime repair is running. Do not rerun the old
  15,552-combination grid.

Evidence: `reports/ARS1_NEXT_OPEN_VALIDATION_20260619.md`,
`reports/ARS1_DIRECTIONAL_DIAGNOSTIC_20260619.md`, and
`configs/autoresearch/range_scalp_v1_regime_repair_v1.json`.

### IVB1 — impulse breakout with pullback

- Legacy best short mirror: 287 trades, `+7.15%`, PF `1.116`, DD `7.13%`;
  February 2026 was red and PF was below 1.2.
- Those results used the older fill convention and are not promotion evidence.
- An 8-combination next-open recheck is queued after ARS1:
  `configs/autoresearch/ivb1_short_next_open_recheck_v1.json`.

### InPlay v3 — level retest

- Auditor mechanics are present: closed bars only, entry-TF ATR for retest,
  timestamp cooldown, next-open backtest fills.
- Corrected server r007/r008 produced PF `1.084–1.085`, net `+1.47..+1.49`;
  both failed. r001-r006 timed out on the server.
- Research-only; no live risk.

### Pump-fade

- The old grid used four env names not consumed by the strategy. Spec and
  cooldown were repaired before rerun.
- All 12 real combinations failed. Maximum PF was about `0.848`; no live risk.

### Breakdown

- Corrected recent-bear variants: PF `0.450`, net `-16.41`.
- Earlier full-grid best: PF `0.679`, net `-6.59`.
- Parameter grinding stopped; next work is entry-logic redesign.

### Elder Triple Screen v2

- 541 valid variants failed.
- PF range about `0.573–0.838`; best still had roughly `-70%` net and `72%` DD
  because of excessive trade count.
- Elder remains disabled. Next iteration is redesign, not a larger grid:
  side-aware trend regime, canonical multi-screen separation, closed-bar
  triggers, timestamp cooldown and bounded frequency, then next-open OOS/WF.

### VWAP and pair arb

- Corrected VWAP first eight variants: PF `0.541–0.585`, net near `-98..-99%`.
- Pair-arb matrix: 180 rows. Best sparse result `+1.06%`, 7/15 positive folds,
  worst fold `-5.06%`; research/fragile, not canary.

## 6. Active server research

Detached screen: `crypto_candidate_recheck_20260619`.

Log: `logs/crypto_candidate_recheck_20260619.log`.

Sequential low-priority queue:

1. `range_scalp_v1_regime_repair_v1` — 64 next-open combinations.
2. `ivb1_short_next_open_recheck_v1` — 8 next-open combinations.

The liquidation collector remains active in
`bybit_liquidations_collector_20260616`. No local `screen` research jobs were
alive at handoff. On continuation, poll the existing server log first and
preserve completed run directories before starting anything new.

## 7. Alpaca state

`alpaca_adaptive_v1` baseline is the actual Alpaca paper order driver. Its
execution-validation clock began on 2026-06-18.

- Virtual strategy capital `$1000`, target allocation `70%`, max 4 positions.
- Actual adaptive positions: AAPL, JPM, UNH; about `$700` total notional.
- Each position has a broker-hosted stop.
- Software stop/trailing management runs every 30 minutes in market hours.
- `lively_config` runs separately as no-order A/B shadow.
- v38/v39 artifacts remain comparison evidence; adaptive baseline owns paper
  positions. The v38 refresh is not the active order manager.
- Fills and stop creation are observed; a complete exit/rotation/recovery cycle
  has not yet occurred.

First formal `$500` review is after five complete US market sessions of adaptive
paper execution, earliest after the 2026-06-26 close. Verify ownership, fills,
broker stop coverage, cancellation/replacement, software trailing, cleanup and
account reconciliation. This is a review point, not automatic approval.

## 8. Continuation sequence

1. Verify service, private positions and heartbeat; do not infer a hard block
   from allocator status.
2. Poll `crypto_candidate_recheck_20260619`; build monthly tables for ARS1 and
   IVB1 without restarting completed sweeps.
3. If ARS1 keeps the same red months, decompose the losing trade stream into
   trend contamination, symbol concentration and execution costs.
4. Keep legacy Range at current small risk with regime-side guard while evidence
   is collected; do not increase risk from the three-trade short sample.
5. Redesign Elder and Breakdown as separate long/short logic; do not tune the
   failed implementations further.
6. Continue adaptive Alpaca ownership checks through 2026-06-26 and keep lively
   as A/B shadow.
7. Update `PROJECT_MAP.md` when module ownership, live status or data flow changes.

## 9. Short development prompt

Work as the senior engineer responsible for this live trading system. Establish
the current source of truth from code, server runtime and reproducible evidence;
separate facts from hypotheses; preserve account safety and existing user work;
and carry each change through implementation, tests, deployment and measurement.
Optimize for robust after-cost portfolio expectancy and operational reliability,
not activity, isolated backtest peaks or optimistic promises.
