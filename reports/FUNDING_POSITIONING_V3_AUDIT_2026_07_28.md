# Funding positioning V3 audit — 2026-07-28

## Verdict

`PASS_RESEARCH_SHADOW` for the preregistered `p70 / 16h` challenger.

This is not a live-money authorization. It is a bounded candidate for an
execution-aware shadow ledger.

The preregistered primary `p70 / 24h` is
`BLOCKED_CONCENTRATION`: its average is positive, but only four of eight
symbols are positive after maker costs.

## Why V3 was required

The two earlier audits contained complementary controls:

- Codex V2 included strict thresholds, funding cashflows, per-symbol
  non-overlap, costs and point-in-time regime labels.
- Claude's funding gates introduced a beta estimated from prior observations.

Neither implementation alone represented the intended portfolio. V3 combines
those controls and also applies the station's three-position limit.

## Results

All figures below include a 6 bps maker round-trip proxy and actual funding
cashflows crossed during the holding interval.

| Setting | Trades | Residual net / trade | Positive symbols | Regime result |
|---|---:|---:|---:|---|
| p60 / 8h | 2,111 | +0.83 bps | 5/8 | bear-dominated |
| p60 / 16h | 975 | +3.54 bps | 6/8 | mixed |
| p70 / 8h | 1,927 | +2.15 bps | 5/8 | bear-dominated |
| **p70 / 16h** | **893** | **+10.50 bps** | **5/8** | **bull, neutral and bear positive** |
| p70 / 24h | 556 | +15.51 bps | 4/8 | concentration failure |
| p85 family | 326–940 | negative | 2–3/8 | failed |
| p90 / 24h | 155 | +7.64 bps | 5/8 | low-power island |

For `p70 / 16h`, residual net by point-in-time regime:

- bull: +10.07 bps, N=201;
- neutral: +4.84 bps, N=233;
- bear: +13.57 bps, N=459.

The same setting with a 16 bps taker round-trip leaves only +0.50 bps per
trade. The hypothesis is therefore maker-dependent.

## Limitations

- Maker fill probability, queue position and adverse selection are not
  modelled.
- The result is a bar-level event audit, not a compounded portfolio curve;
  annual return and drawdown must not be inferred from the summed event
  returns.
- Symbol dispersion remains material: BTC, ETH and LTC are negative on the
  residual maker metric. They must not be removed ex post; a prospective
  eligibility rule or independent holdout is required.

## Next falsifiable step

Create a risk-zero shadow ledger for `p70 / 16h` that records:

1. signal timestamp and point-in-time percentile;
2. simulated maker quote, timeout, fill and adverse selection;
3. actual funding cashflow;
4. three-slot selection and rejected candidates;
5. markout at 8h and 16h;
6. per-symbol and per-regime distribution.

Promotion beyond shadow requires a new owner decision and a separate
execution gate.

Raw receipt:
`reports/research/funding_positioning_v3_20260728/results.json`.
