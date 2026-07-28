# Funding positioning V2 — независимый bounded audit

Verdict: `REPAIR / FILTER_REPLAY_REQUIRED / MONEY_NO_GO`

Source data: Bybit funding and 5m cache for eight frozen symbols, events from
2025-05-28 through 2026-04-24. No private API, broker call or real order.

## Why Claude's terminal wording was too strong

The exploratory script was useful, but it:

- counted common funding values equal to the percentile as extreme;
- allowed overlapping positions on one symbol for holds longer than 8h;
- omitted funding cashflows crossed while the position was open;
- used broad ex-post market windows;
- did not remove market beta;
- summed per-trade returns without a three-slot portfolio lifecycle.

Its conclusion that the original headline was largely directional beta is
reasonable. The stronger conclusion that no standalone or additive feature can
exist is not established by that test.

## Frozen V2 repairs

- strict p90 exceedance instead of `>=` ties;
- no overlapping position on the same symbol;
- next-open entries;
- funding cashflows included;
- point-in-time BTC trailing-30d regime;
- beta-one BTC residual for alts;
- fixed maker 6 bps and taker 16 bps roundtrip scenarios.

## Result

| Hold | N | Shorts | Maker net/trade | Maker beta-residual | Taker net/trade |
|---:|---:|---:|---:|---:|---:|
| 4h | 978 | 16.7% | +1.42 bps | -5.53 bps | -8.58 bps |
| 8h | 978 | 16.7% | +15.35 bps | +2.53 bps | +5.35 bps |
| 12h | 751 | 16.1% | +28.82 bps | +11.60 bps | +18.82 bps |
| 16h | 751 | 16.1% | +41.02 bps | +17.73 bps | +31.02 bps |

The strict rule flips the exploratory side distribution: most signals are
negative-funding longs, not shorts. Therefore the previous `74% shorts` result
described a different population created by percentile ties.

The residual result is not stable across regimes. At 8h the maker residual is
negative in point-in-time bull regimes and positive in neutral/bear regimes.
Longer holds improve the average monotonically, which still raises a
directional/selection concern rather than proving a squeeze.

## Remaining blockers

1. Multiple symbols trigger at the same funding timestamp; the result is not yet
   constrained to the portfolio's three slots.
2. Beta-one residual is a diagnostic, not a fitted PIT beta model.
3. Maker fill probability and adverse selection are not modelled.
4. Holds and percentile are a small family; the 12h/16h headline requires an
   untouched time split and multiple-testing adjustment.
5. The feature has not been joined to immutable ATT1/BREAKDOWN decisions, so
   incremental value is unknown.

## Next falsifiable test

Freeze V2.1 before viewing it:

- at most three simultaneous candidates across the whole universe;
- selection by funding extremeness known at the event;
- rolling PIT beta and symbol/side/regime decomposition;
- discovery/validation/untouched chronological splits;
- then join the frozen feature to ATT1 and BREAKDOWN ledgers.

Promotion is possible only if the filter improves OOS after-cost expectancy
without worsening drawdown. It must not become a standalone money sleeve from
this result.

