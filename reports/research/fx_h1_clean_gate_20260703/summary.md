# FX native harness summary

- rows: 576
- data_dir: `data_cache/forex`
- interval_min: `60`
- coverage_gate: `True`
- cost_gate: `True`

| symbol | setup | rr | sl_atr | hold | coverage | cost | feeR | skip | trades | netR | PF | WR | folds+ | preflight |
|---|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|
| AUDUSD | session_range_fade | 2.5 | 1.6 | 48 | True | True | 0.120 |  | 32 | 6.199 | 1.283 | 0.375 | 3/4 | True |
| AUDUSD | session_range_fade | 2.5 | 1.6 | 96 | True | True | 0.120 |  | 31 | 5.158 | 1.241 | 0.387 | 3/4 | True |
| AUDUSD | session_range_fade | 2.5 | 1.6 | 24 | True | True | 0.120 |  | 35 | 3.794 | 1.163 | 0.400 | 3/4 | True |
| AUDUSD | session_range_fade | 2.5 | 2.0 | 24 | True | True | 0.096 |  | 32 | 3.356 | 1.181 | 0.438 | 2/4 | True |
| AUDUSD | session_range_fade | 2.0 | 2.0 | 24 | True | True | 0.096 |  | 32 | 3.108 | 1.168 | 0.438 | 3/4 | True |
| AUDUSD | session_range_fade | 2.0 | 2.5 | 24 | True | True | 0.077 |  | 31 | 2.803 | 1.188 | 0.484 | 3/4 | True |
| AUDUSD | session_range_fade | 2.5 | 2.5 | 24 | True | True | 0.077 |  | 31 | 2.785 | 1.187 | 0.484 | 2/4 | True |
| AUDUSD | session_range_fade | 1.5 | 2.5 | 24 | True | True | 0.077 |  | 32 | 2.354 | 1.152 | 0.500 | 2/4 | True |
| AUDUSD | session_range_fade | 2.0 | 1.6 | 48 | True | True | 0.120 |  | 33 | 2.101 | 1.096 | 0.394 | 2/4 | True |
| AUDUSD | session_range_fade | 1.5 | 2.0 | 96 | True | True | 0.096 |  | 30 | 2.029 | 1.118 | 0.467 | 1/4 | True |
| AUDUSD | session_range_fade | 1.5 | 2.0 | 48 | True | True | 0.096 |  | 31 | 1.561 | 1.088 | 0.452 | 2/4 | True |
| AUDUSD | session_range_fade | 2.0 | 1.6 | 96 | True | True | 0.120 |  | 32 | 1.559 | 1.073 | 0.406 | 2/4 | True |
| AUDUSD | session_range_fade | 2.0 | 1.6 | 24 | True | True | 0.120 |  | 36 | 1.548 | 1.067 | 0.417 | 1/4 | True |
| AUDUSD | session_range_fade | 1.5 | 2.0 | 24 | True | True | 0.096 |  | 34 | 0.918 | 1.049 | 0.471 | 2/4 | True |
| AUDUSD | session_range_fade | 1.5 | 1.6 | 48 | True | True | 0.120 |  | 36 | -0.832 | 0.962 | 0.444 | 2/4 | True |
| AUDUSD | session_range_fade | 1.5 | 1.6 | 96 | True | True | 0.120 |  | 36 | -0.832 | 0.962 | 0.444 | 2/4 | True |
| AUDUSD | session_range_fade | 2.0 | 1.3 | 48 | True | True | 0.148 |  | 37 | -1.309 | 0.950 | 0.378 | 2/4 | True |
| AUDUSD | session_range_fade | 2.0 | 1.3 | 96 | True | True | 0.148 |  | 37 | -1.309 | 0.950 | 0.378 | 2/4 | True |
| AUDUSD | session_range_fade | 1.5 | 1.6 | 24 | True | True | 0.120 |  | 38 | -1.683 | 0.926 | 0.447 | 2/4 | True |
| AUDUSD | session_range_fade | 2.5 | 1.3 | 48 | True | True | 0.148 |  | 35 | -2.051 | 0.925 | 0.314 | 2/4 | True |

## Outputs

- `reports/research/fx_h1_clean_gate_20260703/summary.csv`
- `reports/research/fx_h1_clean_gate_20260703/coverage.csv`
- `reports/research/fx_h1_clean_gate_20260703/trades.csv`
