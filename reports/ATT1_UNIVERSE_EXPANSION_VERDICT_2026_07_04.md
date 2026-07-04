# ATT1 r001 universe expansion verdict — 2026-07-04

Source prereg:

- `reports/ATT1_UNIVERSE_EXPANSION_PREREG_2026_07_04.md`

Frozen candidate:

- Strategy: `alt_trendline_touch_v1`
- Side: short-only
- Geometry: exact r001 (`pivot 2/3`, `min_pivots=2`, `max_age=16`, `min_r2=0.55`, `touch_atr=0.50`)
- Base symbols excluded: `BTC,ETH,SOL,ADA,LINK,LTC,DOT,SUI`
- Expansion symbols tested as one group: `DOGE,XRP,AVAX,ATOM,BNB,BCH,XLM,1000PEPE,HYPE,TAO,ONDO`
- Window: 360d ending `2026-07-04`
- Execution: next-open
- Base cost: `fee=6bps`, `slippage=2bps`
- Stress cost: `fee=10bps`, `slippage=5bps`

## Gate result

Expansion FAIL.

| run | trades | net | PF | WR | DD | neg months | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| base 6/2 | 353 | +7.93 | 1.081 | 53.8% | 9.16 | 3 | FAIL: PF < 1.15 |
| stress 10/5 | 364 | -9.24 | 0.913 | 52.5% | 13.53 | 6 | FAIL: PF < 1.05 and net < 0 |

Run dirs:

- `backtest_runs/portfolio_20260704_173158_att1_short_r001_universe_expansion_20260705_base_r001`
- `backtest_runs/portfolio_20260704_173346_att1_short_r001_universe_expansion_20260705_stress_r001`

## Per-symbol base result

| symbol | trades | net | PF | WR |
| --- | ---: | ---: | ---: | ---: |
| 1000PEPEUSDT | 32 | +5.02 | 1.708 | 65.6% |
| ATOMUSDT | 30 | -3.85 | 0.620 | 43.3% |
| AVAXUSDT | 29 | +1.92 | 1.254 | 58.6% |
| BCHUSDT | 43 | -5.75 | 0.582 | 44.2% |
| BNBUSDT | 27 | +0.94 | 1.152 | 48.1% |
| DOGEUSDT | 27 | +5.10 | 1.820 | 66.7% |
| HYPEUSDT | 23 | -2.38 | 0.741 | 43.5% |
| ONDOUSDT | 29 | +3.74 | 1.552 | 62.1% |
| TAOUSDT | 39 | +1.28 | 1.110 | 53.8% |
| XLMUSDT | 40 | +0.41 | 1.038 | 55.0% |
| XRPUSDT | 34 | +1.50 | 1.174 | 52.9% |

## Per-symbol stress result

| symbol | trades | net | PF | WR |
| --- | ---: | ---: | ---: | ---: |
| 1000PEPEUSDT | 33 | +3.69 | 1.489 | 63.6% |
| ATOMUSDT | 31 | -6.32 | 0.454 | 38.7% |
| AVAXUSDT | 29 | +0.80 | 1.103 | 58.6% |
| BCHUSDT | 44 | -6.93 | 0.526 | 45.5% |
| BNBUSDT | 31 | -0.64 | 0.915 | 48.4% |
| DOGEUSDT | 28 | +3.65 | 1.547 | 64.3% |
| HYPEUSDT | 24 | -3.27 | 0.664 | 41.7% |
| ONDOUSDT | 28 | +1.98 | 1.282 | 60.7% |
| TAOUSDT | 39 | -0.90 | 0.927 | 51.3% |
| XLMUSDT | 41 | -0.47 | 0.959 | 56.1% |
| XRPUSDT | 36 | -0.83 | 0.915 | 50.0% |

## Interpretation

- The expansion group is not robust enough to add to live ATT1.
- Base-cost result is mildly positive but too weak (`PF 1.081`), and stress-cost result turns negative.
- The apparent positives are concentrated in a few symbols (`DOGE`, `1000PEPE`, `ONDO`, partly `AVAX`), but prereg explicitly forbids cherry-picking symbols after seeing the result.
- Operational decision: do **not** expand `ATT1_SYMBOL_ALLOWLIST`. Keep live ATT1 r001 on the current base universe.
- This does not kill ATT1. It means ATT1 is currently a narrower edge than hoped; risk ramp should remain conservative and based on live telemetry.

## Next allowed research

If this family is revisited:

1. Register a new symbol-selection hypothesis before testing, e.g. volatility/liquidity/regime-selected ATT1 universe.
2. Use symbol-OOS again: train symbols and test symbols must be separate.
3. Keep stress-cost as a hard gate.
