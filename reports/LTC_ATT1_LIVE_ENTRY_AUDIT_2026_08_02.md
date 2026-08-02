# LTCUSDT ATT1 live entry audit — 2026-08-02

> **Superseded geometry interpretation.** The direct execution/protection facts
> below remain valid, but the first verdict treated reproducibility of the
> fitted line as stronger evidence than it was.  The liquidity-aware follow-up
> in `reports/ATT1_GEOMETRY_V2_FORENSIC_2026_08_02.md` shows that horizontal
> liquidity around 44.79-44.82 better explains the reaction and that the entry
> had only about 0.21R room before the equal-low pool at 44.57.  Read the entry
> as a mislabeled/late boundary setup, not a clean ATT1 trendline example.

## Direct truth

- Execution: `Sell 1.1 LTCUSDT @ 44.65`, 2026-08-02 11:51:29 UTC.
- Bybit position after entry: size `1.1`, average `44.65`, status `Normal`.
- Exchange protection: stop-loss `45.04` is present at Bybit.
- Runtime runner: enabled; TP1 `44.204666` for 55%, TP2 `43.711387`
  for 45%; breakeven and ATR trailing arm at `1R`.
- No live parameter, risk, order or universe change was made during this audit.

## Reconstructed causal signal

ATT1 correctly consumed closed H1 bars through `strategies/att1_live.py` and
`strategies/live_kline_utils.py`. The last signal bar began at 10:00 UTC and
closed at approximately `44.66`; actual fill was `44.65`.

The three most recent H1 swing-high anchors were:

| UTC | high |
|---|---:|
| 2026-08-01 04:00 | 44.75 |
| 2026-08-02 02:00 | 44.77 |
| 2026-08-02 07:00 | 44.86 |

Their fitted projection at the signal bar was `44.835945`, slope
`+0.1676%/day`, R2 `0.5842`. ATR14 was about `0.185`; the closed-bar entry was
about `0.95 ATR` below the line and the actual fill about `1.00 ATR` below it.

## Verdict

The entry is **valid under the current production code**, because production
permits short resistance slopes up to `+0.5%/day`, requires R2 at least `0.55`,
and permits entry distance up to `2.0 ATR`.

It is not a clean example of the stated descending-resistance idea: all three
anchors rise, R2 is close to the minimum, and the rejection close is roughly
one ATR below the line. This is a valid boundary case, not proof of a broken
trade and not proof that the boundary is economically useful.

The projected line shown in the report is numerically reproducible. The report
still does not serialize and label the exact pivot timestamps/prices, so the
render is not yet a complete forensic proof of how the line was formed.

## Next falsifiable test

`att1_short_slope_direction_ablation_20260802` freezes the r001 contract and
tests only `ATT1_SHORT_MAX_POS_SLOPE = 0.0, 0.1, 0.25, 0.5`. This is
research-only. Any change requires untouched time OOS, LOSO, regimes, cost
stress and adequate power.

Separately, ATT1's 55-minute decision cadence can discover a newly closed H1
bar with a phase delay of up to roughly 55 minutes. In this case price slippage
from the closed H1 signal (`~44.66`) to fill (`44.65`) was negligible, but the
scheduler deserves a deterministic bar-close audit before changing production.

## Same-window slope-direction interim

The four-arm diagnostic completed after this report was preregistered:

| maximum positive short slope | trades | net | PF | DD | red months |
|---:|---:|---:|---:|---:|---:|
| 0.00%/day | 283 | +26.69 | 1.394 | 6.57 | 1 |
| 0.10%/day | 283 | +26.69 | 1.394 | 6.57 | 1 |
| 0.25%/day | 285 | +26.76 | 1.393 | 6.59 | 1 |
| 0.50%/day, current baseline | 290 | +27.77 | 1.402 | 6.55 | 2 |

The current allowance retained a small same-window lead, but only seven of 290
trades disappear under descending-only geometry. This is not enough to prove
that rising lines are useful: their incremental sample is underpowered and the
current live LTC trade is a boundary case. Production remains unchanged; the
next decision evidence must come from untouched time OOS and signed-slope trade
attribution.
