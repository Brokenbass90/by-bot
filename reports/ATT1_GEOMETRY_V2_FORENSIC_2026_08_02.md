# ATT1 Geometry V2 forensic — 2026-08-02

## Corrected verdict on the LTCUSDT entry

The yellow line was numerically reproducible, but that fact was insufficient
to call the trade a trendline setup.  Reconstructing only the closed H1 bars
available before the order produced:

| Evidence | Value |
|---|---:|
| fitted resistance projection | 44.835945 |
| fitted slope | +0.1676%/day |
| three-pivot R2 | 0.5842 |
| signal-bar high | 44.81 |
| fill | 44.65 |
| distance from projection to entry | 1.01 ATR |
| equal-high liquidity pool | 44.7933, 3 touches |
| equal-low liquidity pool below | 44.57, 2 touches |
| room from entry to first lower pool | about 0.21R |

The line was rising, weak, and was not itself reached.  A horizontal liquidity
zone around 44.79-44.82 better explains the prior reaction.  The order was then
placed close to lower liquidity around 44.57, so the first obstacle appeared
far before the planned 1.2R target.

Classification: **late horizontal-resistance reaction mislabeled as an ATT1
trendline touch**.  The result of the trade, positive or negative, does not
repair the setup attribution.

## Why the earlier PF table did not settle the question

The slope ablation tested only whether changing the maximum accepted positive
slope altered aggregate same-window results.  It did not test whether the
selected line was responsible for the reaction, whether it was reached, or
whether there was room to the next opposing level.  Therefore PF 1.402 for the
current allowance cannot validate this chart or this entry.

## Implemented research challenger

`bot/att1_geometry_v2.py` now requires all of the following for a short:

1. at least three confirmed resistance pivots;
2. a genuinely descending line with an informative fit;
3. the signal candle reaching the projected line zone;
4. entry before the rejection becomes stale;
5. sufficient room before horizontal or equal-low liquidity;
6. separate attribution when an equal-high/horizontal level better explains
   the setup.

The evaluator records exact pivot anchors and the provenance of the origin and
opposing levels so future charts can show evidence rather than a decorative
line.

The challenger is wired behind `ATT1_GEOMETRY_V2_ENABLE=0` by default.  This
preserves the live champion exactly.  No live risk, order, universe, or runtime
parameter was changed.

## Validation contract

The first comparison is a two-arm causal preflight: current champion versus
Geometry V2.  It can reject V2 but cannot promote it.  Any production decision
requires removed-trade attribution, untouched time OOS, symbol LOSO, regime
splits, cost stress, and adequate statistical power.

## Strict preflight result

| arm | trades | net | PF | drawdown | red months |
|---|---:|---:|---:|---:|---:|
| current champion | 290 | +27.77% | 1.402 | 6.55% | 2 |
| all V2 blockers enforced | 45 | +2.58% | 1.218 | 2.52% | 6 |

The all-at-once challenger is too selective and is rejected as a replacement.
It retained positive gross economics but removed 84.5% of trades and worsened
month consistency.  The next preregistered diagnostic decomposes line quality,
touch/lateness, room, and horizontal attribution so one useful guard is not
confused with an over-restrictive bundle.

## Blocker-family decomposition

This is a same-window mechanism diagnostic, not OOS and not live authority.

| enforced family | trades | net | PF | drawdown | red months | gate |
|---|---:|---:|---:|---:|---:|---|
| line quality only | 258 | +25.76% | 1.421 | 4.80% | 3 | PASS |
| touch and lateness | 186 | +10.27% | 1.237 | 4.74% | 4 | PASS |
| room only | 113 | +5.37% | 1.178 | 3.98% | 6 | FAIL |
| horizontal attribution | 232 | +17.47% | 1.301 | 5.67% | 4 | PASS |
| line quality + touch | 170 | +7.65% | 1.189 | 5.13% | 4 | PASS |
| attribution + room | 90 | +3.02% | 1.121 | 5.22% | 6 | FAIL |
| all blockers | 45 | +2.58% | 1.218 | 2.52% | 6 | FAIL |

The useful mechanism is **line quality**, not blanket strictness.  Compared
with the 290-trade champion it retains 258 trades (89.0%), preserves 92.8% of
net result, raises PF from 1.402 to 1.421, and lowers drawdown from 6.55% to
4.80%.  It would reject the audited LTC trade because the alleged resistance
was rising and its three-pivot fit was weak.

This does not yet authorize a live switch.  The next falsifiable step is a
frozen baseline-versus-line-quality comparison on separate earlier and later
time windows, followed by symbol leave-one-out and removed-trade attribution.

## Separate-window validation

| window | arm | trades | net | PF | win rate | drawdown | red months |
|---|---|---:|---:|---:|---:|---:|---:|
| 360d ending 2025-04-30 | champion | 23 | +0.52% | 1.078 | 52.2% | 2.62% | 1 |
| 360d ending 2025-04-30 | line quality | 18 | +0.21% | 1.040 | 50.0% | 2.05% | 1 |
| 92d ending 2026-07-31 | champion | 42 | +8.70% | 2.167 | 71.4% | 2.78% | 0 |
| 92d ending 2026-07-31 | line quality | 37 | +7.67% | 2.188 | 73.0% | 2.79% | 0 |

The recent window preserves strong economics and marginally improves PF and
win rate, but it loses 11.8% of net.  Removed-trade attribution explains why:
the filter directly removed eight baseline trades worth a combined +1.21,
while portfolio slot interactions admitted three replacement trades worth
+0.18.  The earlier window has only 23 baseline trades and is underpowered.

Therefore line quality is a **semantic correctness candidate**, not a proven
profit enhancer.  It should first run as a shadow classifier: valid descending
line, horizontal-liquidity reaction, or rejected geometry.  Horizontal
reactions that make money belong in their own resistance-fade sleeve and must
not silently widen ATT1's meaning.

The code now supports exactly that non-invasive stage through
`ATT1_GEOMETRY_V2_OBSERVE=1`: it appends the class, applicable blockers,
origin, support, room and pivots to the immutable signal reason but never
blocks a champion entry.  The default remains off and no live environment was
changed in this work.

Observer parity passed on the recent 92-day window: both arms produced the
same 42 orders, entry/exit timestamps, prices, quantities, PnL, fees and
outcomes (canonical SHA-256
`36bd7b718369784d60af148a03a71362c7d6164aaffd67a55913c3a71fb41433`).
Only the reason text gains the diagnostic geometry.

## Evidence rendered for future Geometry V2 entries

When the challenger is enabled in research or shadow, the immutable signal
reason now serializes exact pivot anchors, the independently detected reaction
origin, the nearest opposing support, and room in R.  Position geometry parses
all four and the web chart draws the pivots and horizontal structures.  This
prevents a reproducible mathematical line from being presented as sufficient
proof of a market level.
