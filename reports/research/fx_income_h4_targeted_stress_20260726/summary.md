# FX native harness summary

- rows: 16
- data_dir: `data_cache/forex`
- interval_min: `240`
- coverage_gate: `True`
- cost_gate: `True`

| symbol | setup | rr | sl_atr | hold | coverage | cost | feeR | skip | trades | netR | PF | WR | folds+ | preflight |
|---|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|
| GBPUSD | session_range_fade | 1.5 | 1.3 | 12 | True | True | 0.189 |  | 125 | -0.599 | 0.992 | 0.456 | 2/4 | True |
| GBPUSD | session_range_fade | 1.5 | 1.3 | 30 | True | True | 0.189 |  | 119 | -2.251 | 0.970 | 0.462 | 1/4 | True |
| USDJPY | session_range_fade | 2.0 | 1.3 | 30 | True | True | 0.128 |  | 101 | -3.515 | 0.951 | 0.376 | 1/4 | True |
| GBPUSD | session_range_fade | 2.0 | 1.3 | 12 | True | True | 0.189 |  | 114 | -6.863 | 0.905 | 0.404 | 1/4 | True |
| GBPUSD | session_range_fade | 2.0 | 1.0 | 12 | True | True | 0.246 |  | 135 | -7.105 | 0.926 | 0.393 | 1/4 | True |
| GBPUSD | session_range_fade | 1.5 | 1.0 | 30 | True | True | 0.246 |  | 139 | -10.727 | 0.884 | 0.460 | 0/4 | True |
| USDJPY | session_range_fade | 1.5 | 1.3 | 30 | True | True | 0.128 |  | 111 | -10.741 | 0.853 | 0.423 | 1/4 | True |
| GBPUSD | session_range_fade | 2.0 | 1.3 | 30 | True | True | 0.189 |  | 99 | -11.252 | 0.848 | 0.364 | 1/4 | True |
| GBPUSD | session_range_fade | 2.0 | 1.0 | 30 | True | True | 0.246 |  | 130 | -12.681 | 0.872 | 0.377 | 1/4 | True |
| GBPUSD | session_range_fade | 1.5 | 1.0 | 12 | True | True | 0.246 |  | 146 | -13.759 | 0.855 | 0.445 | 0/4 | True |
| USDJPY | session_range_fade | 2.0 | 1.3 | 12 | True | True | 0.128 |  | 115 | -15.551 | 0.807 | 0.383 | 1/4 | True |
| USDJPY | session_range_fade | 1.5 | 1.3 | 12 | True | True | 0.128 |  | 121 | -17.648 | 0.777 | 0.421 | 1/4 | False |
| USDJPY | session_range_fade | 2.0 | 1.0 | 30 | True | True | 0.166 |  | 123 | -20.870 | 0.783 | 0.341 | 1/4 | False |
| USDJPY | session_range_fade | 2.0 | 1.0 | 12 | True | True | 0.166 |  | 134 | -28.271 | 0.729 | 0.343 | 1/4 | False |
| USDJPY | session_range_fade | 1.5 | 1.0 | 30 | True | True | 0.166 |  | 138 | -35.681 | 0.653 | 0.377 | 1/4 | False |
| USDJPY | session_range_fade | 1.5 | 1.0 | 12 | True | True | 0.166 |  | 142 | -39.023 | 0.630 | 0.373 | 0/4 | False |

## Outputs

- `reports/research/fx_income_h4_targeted_stress_20260726/summary.csv`
- `reports/research/fx_income_h4_targeted_stress_20260726/coverage.csv`
- `reports/research/fx_income_h4_targeted_stress_20260726/trades.csv`
