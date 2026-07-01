# ARF2 + server research status — 2026-07-01 PM

## Server facts

Checked server `/root/by-bot`.

Live:

- `bybot.service`: active.
- Proof-of-life: `ALIVE`, regime `bear_chop`, `dry_run=False`, `open_trades=0`.
- Live risk sleeve: `att1 x0.10`.
- Shadow/risk=0: `bounce1`, `flat`, `ivb1`, `midterm`, `range`.
- Last trade event: ~11.6 days ago, `range APEUSDT` close.
- Journal tail: live-risk subtotal `att1_trendline_touch: -0.7909 over 5 trades`.

Research:

- Active process: `scripts/run_strategy_autoresearch.py --spec configs/autoresearch/package_att1_strong_short_ars1_additivity_20260629.json`.
- Active child run at check time: `r047`.
- Last completed checked run: `r046`.
- `r046`: 360d, `alt_trendline_touch_v1 + alt_range_scalp_v1`, 8 symbols, next-open, 6/2 bps.
  - trades: 625
  - net: +8.70%
  - PF: 1.077
  - WR: 44.6%
  - max DD: 9.92%

Verdict: server is not idle. It is running the ATT1+ARS1 additivity sweep. The current best observed summary is not canary-grade yet: PF is thin and DD is near 10%.

## RANGE scan interpretation

Telegram `RANGE scan found=...` is a scout/universe signal, not an entry signal.

It means: these symbols look range-like and are worth feeding into range/bounce/fade sleeves.

It does **not** mean:

- ARF2 should enter immediately;
- the web screener setup card bypasses strategy filters;
- the level/rejection/RR/volume/cooldown checks passed.

Live strategy still needs a valid level, touch/rejection, acceptable RR/stop, volume, and risk gates.

## Local ARF2 smoke diagnostics

Universe used:

`ADAUSDT,DOGEUSDT,SUIUSDT,LINKUSDT,SOLUSDT,DOTUSDT,LTCUSDT,ONDOUSDT`

### Direct no-signal diagnostic

OLD ARF2:

- checked bars: 30,280
- raw signals: 2
- main blockers:
  - `level_not_found`: 24,290
  - `regime_history_short`: 1,656
  - `no_rejection`: 309

NEW ARF2 variants:

| Variant | Raw signals | Notes |
|---|---:|---|
| old | 2 | essentially dead |
| unified | 18 | levels become visible across symbols |
| unified + level_entry | 28 | more raw signals, but fillability matters |
| unified + relaxed range | 24 | frequency improves, still needs PnL gate |

Interpretation: old ARF2 mostly failed because its level detector was too narrow. `unified_levels` materially increases opportunity detection.

### Limit-entry fillability

For `unified + level_entry` raw signals:

| Validity bars | Raw signals | Fillable |
|---:|---:|---:|
| 4 | 28 | 3 |
| 12 | 28 | 9 |
| 24 | 28 | 12 |

Interpretation: limit-at-level is conservative. Default validity=4 is probably too short for ARF2 fade; 12-24 bars should be tested in A/B.

### Portfolio replay

OLD ARF2, 9 symbols, 180d:

- trades: 0

NEW `unified_levels` without level-entry:

- trades: 15
- net: -2.48
- PF: 0.588
- WR: 40.0%
- DD: 3.73
- bad symbols: `SUIUSDT`, `ONDOUSDT`
- positive symbols in this tiny sample: `ADAUSDT`, `DOTUSDT`, `LINKUSDT`

NEW `unified_levels + retest_quality=0.55`:

- trades: 1
- net: +0.58

NEW `unified_levels + retest_quality=0.35`:

- trades: 1
- net: +0.58

Interpretation: `retest_quality` is too restrictive for ARF2 as currently used, or it is measuring the wrong kind of fade/rejection. It improves quality but kills frequency.

## Current ARF2 verdict

Positive:

- We found why ARF2/flat “pila” was mostly silent: old resistance detector was too narrow.
- `unified_levels` does increase raw opportunities.
- RANGE scan is useful as a universe scout.

Negative:

- First PnL sanity with unified levels is negative.
- Retest quality currently over-filters.
- Level-entry fill window needs tuning and a proper replay path.

No live/canary. Next step is not OOS yet.

## Next step

Build a dedicated ARF2 sequential A/B diagnostic runner:

1. OLD baseline.
2. `+unified_levels`.
3. `+level_entry` with validity `{4,12,24}`.
4. `+range_filter`.
5. `+retest_quality` with `{0.25,0.35,0.45}` or ARF2-specific fade scorer.
6. Per step:
   - raw signal count;
   - fillable count;
   - closed-trade PnL/PF if simulated;
   - per-symbol PnL;
   - filter drop reasons.

Only after a variant has enough frequency and cheap PF sanity should it enter preflight/OOS.

