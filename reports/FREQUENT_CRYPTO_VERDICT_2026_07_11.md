# Frequent crypto prereg — final immutable verdict (2026-07-11)

## Answer first

**Verdict: `NO_PROMOTION` for all three evaluated sleeves.**

- `ARS1 long-only + ADX<=25`: rejected. The filter made the annual stress result worse than its same-side control and removed too many trades.
- `ARS1 short-only + ADX<=25`: rejected. The filter turned a near-flat control into a clearly losing sleeve.
- `ASB2 long-only, descending channels blocked`: the causal change improved the very bad control, but the repaired sleeve is still decisively unprofitable under both base and stress costs.

None of these results authorizes shadow, canary, live wiring, or a risk increase. The experiment itself is valid and useful: it prevents three weak candidates from consuming live capital.

## Evidence integrity

Evidence set: `reports/research/frequent_crypto_prereg_20260711/20260711_112429`.

- `COMPLETE` exists; all `15/15` preregistered cases have a matching `summary.csv` and `trades.csv`.
- Run interval: M5 cache, end `2026-07-04`; annual `360d` and fresh `90d` windows.
- Frozen universe: `13` symbols. Every symbol has exactly `103,680/103,680` expected M5 rows, coverage `1.000000`, and maximum internal gap `0`.
- Execution: closed signal bar, fill at next M5 open; base costs `6 bps fee + 2 bps slippage` per side; stress costs `10 + 5 bps` per side.
- Starting equity `$100`, risk `0.5%`, cap `$30`, max positions `4`; allocator and regime router disabled.
- Research only: cache-only, risk-zero, no broker/live calls.
- Frozen hashes recorded at launch still match the four runtime sources. Archived preregistration SHA256 equals the source spec SHA256: `d56de6d1769442f5ecb610cb38ed4446526716dfc0ec74dca88bd838a4f8b417`.
- Direction audit passed: every ARS1 long and ASB2 trade is `long`; every ARS1 short trade is `short`. There is no side mixing in any of the 15 files.

The run is therefore valid negative evidence, not an infrastructure failure.

## All frozen cases

`DD` is in starting-equity percentage points because every case starts at `$100`. `+sym` and `+mon` mean symbols/months with positive net PnL among symbols/months that traded. Concentration is the largest contributor's share of gross profit, not net PnL.

| Case | N | Net | PF | WR | DD | +sym | +mon | Top symbol GP | Top month GP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ARS1 long control, 360d base | 150 | -8.21 | 0.765 | 20.0% | 15.82 | 4/12 | 2/12 | AVAX 18.2% | 2026-02 36.6% |
| ARS1 long control, 360d stress | 177 | -18.11 | 0.604 | 19.2% | 22.18 | 2/13 | 2/12 | AVAX 17.2% | 2026-06 34.6% |
| ARS1 long ADX25, 360d base | 43 | -6.47 | 0.374 | 18.6% | 7.41 | 3/11 | 1/8 | ONDO 29.3% | 2026-06 63.8% |
| ARS1 long ADX25, 360d stress | 44 | -8.55 | 0.292 | 18.2% | 9.09 | 1/11 | 0/9 | ONDO 29.7% | 2026-06 63.9% |
| ARS1 long ADX25, 90d stress | 11 | -0.47 | 0.821 | 36.4% | 1.20 | 3/7 | 0/2 | ONDO 48.2% | 2026-06 100.0% |
| ARS1 short control, 360d base | 103 | +3.09 | 1.139 | 28.2% | 4.73 | 6/12 | 7/13 | TAO 31.5% | 2026-03 17.4% |
| ARS1 short control, 360d stress | 106 | +0.13 | 1.005 | 29.2% | 5.90 | 5/12 | 7/13 | TAO 31.1% | 2026-03 16.6% |
| ARS1 short ADX25, 360d base | 38 | -2.56 | 0.682 | 26.3% | 2.98 | 3/9 | 5/11 | ONDO 27.9% | 2026-05 24.7% |
| ARS1 short ADX25, 360d stress | 38 | -4.16 | 0.550 | 26.3% | 4.16 | 2/9 | 3/11 | ONDO 27.7% | 2026-05 25.1% |
| ARS1 short ADX25, 90d stress | 13 | -1.51 | 0.514 | 30.8% | 2.54 | 1/5 | 1/2 | ONDO 71.6% | 2026-05 79.5% |
| ASB2 descending control, 360d base | 1,165 | -50.41 | 0.721 | 49.2% | 51.96 | 3/13 | 2/13 | 1000PEPE 12.5% | 2025-11 14.3% |
| ASB2 descending control, 360d stress | 1,416 | -93.44 | 0.471 | 44.1% | 93.44 | 0/13 | 0/13 | HYPE 13.0% | 2025-11 18.2% |
| ASB2 no-descending, 360d base | 791 | -31.18 | 0.754 | 50.3% | 32.66 | 3/13 | 4/13 | HYPE 14.9% | 2025-11 13.9% |
| ASB2 no-descending, 360d stress | 906 | -68.10 | 0.524 | 48.2% | 68.28 | 0/13 | 1/13 | HYPE 14.9% | 2025-11 14.8% |
| ASB2 no-descending, 90d stress | 123 | -8.55 | 0.639 | 49.6% | 10.32 | 2/13 | 1/4 | 1000PEPE 21.1% | 2026-06 52.7% |

## Gate audit

### ARS1 long-only, ADX25

| Frozen gate | Required | Actual | Result |
|---|---:|---:|---|
| Annual base trades | >= 30 | 43 | PASS |
| Annual base PF | >= 1.25 | 0.374 | **FAIL** |
| Annual stress PF | >= 1.05 | 0.292 | **FAIL** |
| Annual stress net | >= 0 | -8.55 | **FAIL** |
| Annual max DD | <= 10% | 9.09% | PASS |
| Fresh 90d stress trades | >= 8 | 11 | PASS |
| Fresh 90d stress PF | >= 1.00 | 0.821 | **FAIL** |
| Fresh 90d stress net | >= 0 | -0.47 | **FAIL** |
| Stress PF vs ADX-off control | improve over 0.604 | 0.292 | **FAIL** |
| Stress trade retention | >= 30% | 44/177 = 24.9% | **FAIL** |

The annual stress candidate had no positive month (`0/9`) and only one positive symbol (`1/11`). Even its fresh-window gross profit came entirely from June; this is not a stable edge.

### ARS1 short-only, ADX25

| Frozen gate | Required | Actual | Result |
|---|---:|---:|---|
| Annual base trades | >= 30 | 38 | PASS |
| Annual base PF | >= 1.25 | 0.682 | **FAIL** |
| Annual stress PF | >= 1.05 | 0.550 | **FAIL** |
| Annual stress net | >= 0 | -4.16 | **FAIL** |
| Annual max DD | <= 10% | 4.16% | PASS |
| Fresh 90d stress trades | >= 8 | 13 | PASS |
| Fresh 90d stress PF | >= 1.00 | 0.514 | **FAIL** |
| Fresh 90d stress net | >= 0 | -1.51 | **FAIL** |
| Stress PF vs ADX-off control | improve over 1.005 | 0.550 | **FAIL** |
| Stress trade retention | >= 30% | 38/106 = 35.8% | PASS |

The ADX gate removed `64.2%` of control trades but removed the edge rather than the noise. Fresh 90d profit is highly concentrated: ONDO supplies `71.6%` of gross profit, while May supplies `79.5%`; the sleeve still loses overall.

The ADX-off short control deserves accurate wording: annual base `+3.09`, PF `1.139`; annual stress `+0.13`, PF `1.005`. That is near break-even, not a promotion result. It misses the preregistered PF gates (`1.25` base and `1.05` stress), has no scheduled fresh-90d control gate, and cannot be promoted selectively after seeing this outcome.

### ASB2 long-only, descending blocked

| Frozen gate | Required | Actual | Result |
|---|---:|---:|---|
| Annual base trades | >= 40 | 791 | PASS |
| Annual base PF | >= 1.25 | 0.754 | **FAIL** |
| Annual stress PF | >= 1.05 | 0.524 | **FAIL** |
| Annual stress net | >= 0 | -68.10 | **FAIL** |
| Annual max DD | <= 10% | 68.28% | **FAIL** |
| Fresh 90d stress trades | >= 10 | 123 | PASS |
| Fresh 90d stress PF | >= 1.00 | 0.639 | **FAIL** |
| Fresh 90d stress net | >= 0 | -8.55 | **FAIL** |
| Stress PF vs descending control | improve over 0.471 | 0.524 | PASS |
| Stress DD vs descending control | improve over 93.44% | 68.28% | PASS |
| Stress trade retention | >= 30% | 906/1,416 = 64.0% | PASS |

The causal repair works in the narrow sense: it reduces cadence and damage. It does not create an edge. Under annual stress every one of the `13/13` symbols is net negative; only `1/13` active months is positive. The 90d window remains `-8.55` with PF `0.639`.

## What the result means

1. ADX<=25 is not the right repair for ARS1 on either side. Do not tune the threshold around this outcome in the same evidence window.
2. Blocking descending channels is necessary risk hygiene for ASB2 long-only, but insufficient. The current entry/exit contract should remain research-only and risk-zero.
3. The short ADX-off control is the least bad measurement, but transaction-cost robustness is essentially zero. A separate future-cutoff preregistration would be required before treating it as a candidate.
4. High cadence alone is not progress: ASB2 produced hundreds of trades while destroying expectancy. Frequency remains subordinate to stress PF, breadth, temporal stability, and live/backtest parity.
5. A future research PASS, if one appears, must still pass a separate implementation-parity audit, risk-zero shadow observation, exchange-cost/fill audit, and breaker/restart-state review before any canary. This run did not reach that stage.

## Final machine-readable decision

```json
{
  "experiment": "frequent_crypto_side_specific_20260711",
  "evidence_stamp": "20260711_112429",
  "data_gate": "PASS",
  "execution_integrity": "PASS",
  "side_purity": "PASS",
  "ars1_long_adx25": "NO_PROMOTION",
  "ars1_short_adx25": "NO_PROMOTION",
  "asb2_no_descending_long": "NO_PROMOTION",
  "research_pass_candidates": 0,
  "shadow_eligible_candidates": 0,
  "live_eligible_candidates": 0
}
```
