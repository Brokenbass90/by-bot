# Sanitized external audit packet — 2026-08-14

This packet contains no API keys, account identifiers, order identifiers, current positions, or broker mutation capability. It is suitable for a proposal-only external model or human reviewer.

## Questions for the reviewer

1. Does the ATT1 evidence support keeping the tiny canary while historical robustness is repaired, or is there a hidden contract mismatch that invalidates the forward cohort?
2. Is a causal momentum-stall exit a materially different mechanism from shortening TP2, and what single frozen definition would best falsify it?
3. Is the proposed sloped-break V2 contract sufficiently distinct from ATT1 and from the failed legacy 64-combination sweep?
4. Which one of Inplay, XSEC/funding, and sloped-break V2 has the highest information value per engineering day?
5. Which Alpaca blocker can most plausibly explain the difference between the clean daily proxy and the live contract?

## ATT1 source and evidence map

- Strategy: `strategies/alt_trendline_touch_v1.py`
- Shared geometry: `bot/att1_geometry_v2.py`
- Backtest engine: `backtest/run_portfolio.py`, `backtest/portfolio_engine.py`
- Current live lifecycle aggregate: `reports/evidence/ATT1_LIVE_LIFECYCLE_20260814.json`
- TP2 preregistration: `research_lab/prereg/PREREG_ATT1_TP2_DISTANCE_V1_2026_08_14.md`
- TP2 result: `reports/evidence/ATT1_TP2_DISTANCE_PREHOLDOUT_20260814.json`
- Old narrow result narrative: `reports/CLAUDE_PLAN_AND_RESULTS_2026_08_10.md`
- Corrected Geometry V2 pre-holdout inputs/results: `research_lab/results/att1_pivot_sequence_preholdout_v1_20260813/`

### ATT1 facts that must not be blended

| Evidence | Result | Meaning |
|---|---:|---|
| Old narrow, historically tuned anchor | 308 trades, +30.20R, +0.098R/trade | Discovery/anchor evidence, not a clean holdout |
| Corrected Geometry V2, fixed eight-major pre-holdout | 393 trades, -2.468R, PF(R) 0.988 | Net historical robustness not established |
| Current clean forward cohort | 5 closes, +2.950R, PF(R) 3.289 | Encouraging but too small for promotion |
| TP2 2.5R → 1.8R challenger | -1.522R incremental, drawdown nearly unchanged | Reject closer TP2; no live change |

The forward cohort has four profitable closes and one losing close. Four of five armed the trailing runner; TP2 was hit zero times. MFE is only a lower bound from runner events, not complete bar replay.

## Inplay evidence

- Prospective collector: `scripts/collect_inplay_prospective_shadow.py`
- Prospective status: `runtime/inplay_prospective_shadow_v1/status.json`
- Parity audit: `reports/evidence/INPLAY_PROSPECTIVE_PARITY_20260814.json`

Current prospective result is zero signals. Code hashes match the historical reference. The same code emitted 32, 40, 62, and 81 raw signals across four earlier non-overlapping 35-day slices (0.91–2.31/day). Current no-signal diagnostics are dominated by weak impulse and no-breakout-side filters. This is frequency/parity evidence only, not edge.

## Sloped-break V2 measured result

The external chart hypothesis is not ATT1. ATT1 fades a descending resistance line; the proposed strategy waits for a 4h sloped structure break, a retest, and lower-timeframe structural confirmation before entering in the break direction.

The frozen V2 contract was implemented and replayed without a grid on the eight-major pre-holdout window. It produced 18 accepted trades, -2.739R, PF(R) 0.704; long was -0.536R and short -2.203R. A separate state-transition audit counted 131 qualifying breaks, 35 held first retests, and 20 signals before portfolio overlap/slot handling. The contract is rejected, but the concept is not globally closed: any V3 must be one preregistered change to the retest definition, not a threshold sweep or favorable-symbol selection. Evidence: `reports/evidence/SLOPED_BREAK_RETEST_V2_PREHOLDOUT_20260814.json` and `reports/evidence/SLOPED_BREAK_RETEST_V2_FUNNEL_20260814.json`.

## Alpaca evidence

- Clean daily proxy: `research_lab/results/alpaca_clean_v38_proxy_v1_20260813/result.json`
- Independent arithmetic audit: `research_lab/results/alpaca_clean_v38_proxy_v1_20260813/independent_audit.json`
- Materialization status: `research_lab/data/alpaca_pit_daily_v1/status.json`

The proxy covers 962 clean symbols and 25 months. Base result is +23.476% cumulative, 11.144% annualized, max drawdown 23.711%, PF 1.270, eight red months. Stress 10 bps/side is +21.857% cumulative with 23.800% drawdown. It is not the exact live contract: 93% of selected slots lack sector classification, full PIT membership/corporate actions are unresolved, and daily bars cannot reproduce 15-minute live stop sampling.

## XSEC/funding evidence

- Funding archive validation: `reports/evidence/BYBIT_FUNDING_LISTINGS_ARCHIVE_VALIDATION_20260812.json`
- Spot daily materialization: `research_lab/data/bybit_spot_daily_preholdout_2023_20250930/status.json`
- XSEC recount: `research_lab/results/xsec_recount/xsec_recount.json`

Funding contains 137 current symbols and 413,356 observations, but the universe is survivor-only and PIT is not ready. Exact Bybit spot daily mapping currently exists for 74 of 137 requested perp symbols. Funding-adjusted XSEC/carry is therefore not capital-ready.

## Strategy inventory

`reports/evidence/STRATEGY_INVENTORY_20260814.json` contains 92 inventory rows: 90 current strategy files plus two census-only names. The adapter smoke reports 31 signal-emitting, 29 zero-signal, 29 no-class, one crashing, and two not probed. These are liveness labels, not profitability or live-readiness verdicts.

## Required reviewer output

Return only:

1. confirmed contract defects;
2. one best next falsifiable experiment per lane;
3. any leakage, selection, execution, or accounting risk;
4. a priority ranking by information gain per engineering day;
5. no live/risk/order recommendation without an explicit passed gate.
