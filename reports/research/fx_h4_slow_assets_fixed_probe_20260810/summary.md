# FX native harness summary

- rows: 12
- data_dir: `data_cache/forex`
- interval_min: `240`
- coverage_gate: `True`
- cost_gate: `True`

| symbol | setup | rr | sl_atr | hold | coverage | cost | feeR | skip | trades | netR | PF | WR | folds+ | preflight |
|---|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|
| EURJPY | trend_pullback | 2.0 | 1.5 | 30 | True | True | 0.167 |  | 13 | 3.366 | 1.432 | 0.462 | 2/4 | False |
| GBPUSD | trend_pullback | 2.0 | 1.5 | 30 | True | True | 0.164 |  | 9 | 1.732 | 1.302 | 0.444 | 3/4 | False |
| USDJPY | session_breakout_retest | 2.0 | 1.5 | 30 | True | True | 0.111 |  | 10 | 1.321 | 1.212 | 0.400 | 2/4 | False |
| EURUSD | session_breakout_retest | 2.0 | 1.5 | 30 | True | True | 0.185 |  | 4 | 1.221 | 1.512 | 0.500 | 2/4 | False |
| EURUSD | trend_pullback | 2.0 | 1.5 | 30 | True | True | 0.185 |  | 10 | 0.794 | 1.118 | 0.400 | 2/4 | False |
| XAUUSD | session_breakout_retest | 2.0 | 1.5 | 30 | True | True | 0.041 |  | 5 | 0.625 | 1.192 | 0.400 | 2/4 | False |
| USDJPY | trend_pullback | 2.0 | 1.5 | 30 | True | True | 0.111 |  | 13 | 0.593 | 1.082 | 0.385 | 2/4 | False |
| EURJPY | session_breakout_retest | 2.0 | 1.5 | 30 | True | True | 0.167 |  | 8 | -0.012 | 0.998 | 0.375 | 3/4 | False |
| XAUUSD | trend_pullback | 2.0 | 1.5 | 30 | True | True | 0.041 |  | 10 | -0.746 | 0.885 | 0.300 | 1/4 | False |
| GBPJPY | trend_pullback | 2.0 | 1.5 | 30 | True | True | 0.165 |  | 14 | -1.582 | 0.826 | 0.357 | 1/4 | False |
| GBPUSD | session_breakout_retest | 2.0 | 1.5 | 30 | True | True | 0.164 |  | 7 | -2.018 | 0.646 | 0.286 | 1/4 | False |
| GBPJPY | session_breakout_retest | 2.0 | 1.5 | 30 | True | True | 0.165 |  | 10 | -7.188 | 0.208 | 0.100 | 1/4 | False |

## Outputs

- `reports/research/fx_h4_slow_assets_fixed_probe_20260810/summary.csv`
- `reports/research/fx_h4_slow_assets_fixed_probe_20260810/coverage.csv`
- `reports/research/fx_h4_slow_assets_fixed_probe_20260810/trades.csv`
