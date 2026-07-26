# FX native harness summary

- rows: 360
- data_dir: `data_cache/forex`
- interval_min: `240`
- coverage_gate: `True`
- cost_gate: `True`

| symbol | setup | rr | sl_atr | hold | coverage | cost | feeR | skip | trades | netR | PF | WR | folds+ | preflight |
|---|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|
| GBPUSD | session_range_fade | 1.5 | 1.3 | 12 | True | True | 0.091 |  | 125 | 10.760 | 1.160 | 0.464 | 3/4 | True |
| GBPUSD | session_range_fade | 2.0 | 1.0 | 12 | True | True | 0.118 |  | 135 | 8.882 | 1.103 | 0.400 | 3/4 | True |
| GBPUSD | session_range_fade | 1.5 | 1.3 | 30 | True | True | 0.091 |  | 119 | 8.540 | 1.123 | 0.462 | 2/4 | True |
| GBPUSD | session_range_fade | 2.5 | 1.3 | 12 | True | True | 0.091 |  | 111 | 7.607 | 1.117 | 0.405 | 2/4 | True |
| GBPUSD | session_range_fade | 1.5 | 1.0 | 30 | True | True | 0.118 |  | 139 | 5.771 | 1.069 | 0.460 | 3/4 | True |
| USDJPY | session_range_fade | 2.0 | 1.3 | 30 | True | True | 0.061 |  | 101 | 4.391 | 1.065 | 0.376 | 3/4 | True |
| GBPUSD | session_range_fade | 2.0 | 1.3 | 12 | True | True | 0.091 |  | 114 | 3.585 | 1.054 | 0.412 | 3/4 | True |
| GBPUSD | session_range_fade | 1.5 | 1.0 | 12 | True | True | 0.118 |  | 146 | 3.545 | 1.041 | 0.452 | 3/4 | True |
| GBPUSD | session_range_fade | 2.0 | 1.0 | 30 | True | True | 0.118 |  | 130 | 2.753 | 1.031 | 0.377 | 3/4 | True |
| USDJPY | session_range_fade | 2.5 | 1.3 | 30 | True | True | 0.061 |  | 97 | 1.962 | 1.028 | 0.320 | 2/4 | True |
| GBPUSD | session_range_fade | 2.5 | 1.0 | 12 | True | True | 0.118 |  | 127 | 1.489 | 1.017 | 0.346 | 3/4 | True |
| GBPUSD | session_range_fade | 2.5 | 1.0 | 30 | True | True | 0.118 |  | 114 | 0.952 | 1.011 | 0.325 | 2/4 | True |
| GBPUSD | session_range_fade | 2.0 | 0.8 | 12 | True | True | 0.147 |  | 159 | 0.170 | 1.002 | 0.384 | 2/4 | True |
| GBPUSD | session_range_fade | 2.0 | 0.8 | 30 | True | True | 0.147 |  | 156 | -0.440 | 0.996 | 0.378 | 2/4 | True |
| GBPUSD | session_range_fade | 2.5 | 0.8 | 12 | True | True | 0.147 |  | 150 | -1.637 | 0.986 | 0.333 | 2/4 | True |
| GBPUSD | session_range_fade | 1.5 | 0.8 | 12 | True | True | 0.147 |  | 173 | -1.720 | 0.984 | 0.451 | 2/4 | True |
| GBPUSD | session_range_fade | 1.5 | 0.8 | 30 | True | True | 0.147 |  | 173 | -1.720 | 0.984 | 0.451 | 2/4 | True |
| USDJPY | session_range_fade | 1.5 | 1.3 | 30 | True | True | 0.061 |  | 111 | -2.000 | 0.971 | 0.423 | 1/4 | True |
| GBPUSD | session_range_fade | 2.0 | 1.3 | 30 | True | True | 0.091 |  | 99 | -2.227 | 0.967 | 0.364 | 1/4 | True |
| GBPUSD | session_range_fade | 2.5 | 0.8 | 30 | True | True | 0.147 |  | 146 | -4.991 | 0.956 | 0.315 | 3/4 | True |

## Outputs

- `reports/research/fx_income_h4_diag_base_20260726/summary.csv`
- `reports/research/fx_income_h4_diag_base_20260726/coverage.csv`
- `reports/research/fx_income_h4_diag_base_20260726/trades.csv`
