# FX native harness summary

- rows: 144
- data_dir: `data_cache/forex_yf_1h_20260703`
- interval_min: `60`
- coverage_gate: `True`
- cost_gate: `True`

| symbol | setup | rr | sl_atr | hold | coverage | cost | feeR | skip | trades | netR | PF | WR | folds+ | preflight |
|---|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|
| AUDUSD | session_range_fade | 2.5 | 2.5 | 96 | True | True | 0.126 |  | 334 | -7.432 | 0.970 | 0.314 | 2/4 | True |
| AUDUSD | session_range_fade | 2.0 | 2.5 | 96 | True | True | 0.126 |  | 367 | -10.511 | 0.959 | 0.357 | 2/4 | True |
| EURUSD | session_range_fade | 2.0 | 2.5 | 96 | True | True | 0.153 |  | 393 | -12.065 | 0.957 | 0.377 | 1/4 | True |
| AUDUSD | session_range_fade | 2.5 | 2.0 | 96 | True | True | 0.158 |  | 412 | -15.038 | 0.952 | 0.311 | 3/4 | True |
| AUDUSD | session_range_fade | 2.0 | 2.5 | 48 | True | True | 0.126 |  | 398 | -16.022 | 0.939 | 0.372 | 1/4 | True |
| EURUSD | session_range_fade | 2.5 | 2.5 | 96 | True | True | 0.153 |  | 368 | -17.926 | 0.938 | 0.321 | 1/4 | True |
| USDJPY | session_range_fade | 2.5 | 2.5 | 48 | True | True | 0.079 |  | 357 | -21.642 | 0.912 | 0.350 | 2/4 | True |
| EURUSD | session_range_fade | 1.5 | 2.5 | 96 | True | True | 0.153 |  | 435 | -23.067 | 0.918 | 0.439 | 1/4 | True |
| AUDUSD | session_range_fade | 2.5 | 2.0 | 48 | True | True | 0.158 |  | 439 | -30.018 | 0.909 | 0.312 | 1/4 | True |
| EURUSD | session_range_fade | 2.0 | 2.5 | 48 | True | True | 0.153 |  | 426 | -31.587 | 0.895 | 0.378 | 1/4 | True |
| AUDUSD | session_range_fade | 1.5 | 2.5 | 96 | True | True | 0.126 |  | 406 | -31.795 | 0.879 | 0.406 | 1/4 | True |
| AUDUSD | session_range_fade | 2.0 | 2.5 | 24 | True | True | 0.126 |  | 474 | -33.480 | 0.877 | 0.401 | 1/4 | True |
| AUDUSD | session_range_fade | 2.5 | 2.5 | 24 | True | True | 0.126 |  | 472 | -33.759 | 0.877 | 0.396 | 2/4 | True |
| AUDUSD | session_range_fade | 2.0 | 2.0 | 96 | True | True | 0.158 |  | 440 | -36.096 | 0.887 | 0.345 | 1/4 | True |
| AUDUSD | session_range_fade | 2.5 | 2.5 | 48 | True | True | 0.126 |  | 385 | -36.163 | 0.865 | 0.338 | 2/4 | True |
| USDJPY | session_range_fade | 2.5 | 2.5 | 96 | True | True | 0.079 |  | 316 | -36.310 | 0.851 | 0.294 | 0/4 | True |
| AUDUSD | session_range_fade | 1.5 | 2.5 | 48 | True | True | 0.126 |  | 422 | -36.451 | 0.863 | 0.408 | 1/4 | True |
| EURUSD | session_range_fade | 1.5 | 2.5 | 48 | True | True | 0.153 |  | 453 | -36.694 | 0.874 | 0.433 | 1/4 | True |
| USDJPY | session_range_fade | 2.0 | 2.5 | 48 | True | True | 0.079 |  | 376 | -38.811 | 0.849 | 0.356 | 1/4 | True |
| AUDUSD | session_range_fade | 2.0 | 2.0 | 48 | True | True | 0.158 |  | 455 | -39.454 | 0.879 | 0.347 | 1/4 | True |

## Outputs

- `reports/research/fx_yf_1h_session_range_20260703/summary.csv`
- `reports/research/fx_yf_1h_session_range_20260703/coverage.csv`
- `reports/research/fx_yf_1h_session_range_20260703/trades.csv`
