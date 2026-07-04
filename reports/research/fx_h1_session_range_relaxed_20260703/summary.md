# FX native harness summary

- rows: 108
- data_dir: `data_cache/forex_1h`
- interval_min: `60`
- coverage_gate: `True`
- cost_gate: `True`

| symbol | setup | rr | sl_atr | hold | coverage | cost | feeR | skip | trades | netR | PF | WR | folds+ | preflight |
|---|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|
| EURUSD | session_range_fade | 2.0 | 2.5 | 96 | True | True | 0.086 |  | 393 | -9.950 | 0.965 | 0.379 | 1/4 | True |
| EURUSD | session_range_fade | 2.5 | 2.5 | 96 | True | True | 0.086 |  | 367 | -17.685 | 0.938 | 0.322 | 2/4 | True |
| EURUSD | session_range_fade | 1.5 | 2.5 | 96 | True | True | 0.086 |  | 435 | -21.452 | 0.923 | 0.441 | 1/4 | True |
| USDJPY | session_range_fade | 2.5 | 2.5 | 48 | True | True | 0.065 |  | 357 | -21.642 | 0.912 | 0.350 | 2/4 | True |
| EURUSD | session_range_fade | 2.0 | 2.5 | 48 | True | True | 0.086 |  | 426 | -29.472 | 0.902 | 0.380 | 1/4 | True |
| EURUSD | session_range_fade | 1.5 | 2.5 | 48 | True | True | 0.086 |  | 453 | -35.079 | 0.880 | 0.435 | 1/4 | True |
| USDJPY | session_range_fade | 2.5 | 2.5 | 96 | True | True | 0.065 |  | 316 | -36.310 | 0.851 | 0.294 | 0/4 | True |
| EURUSD | session_range_fade | 2.5 | 2.0 | 96 | True | True | 0.108 |  | 448 | -38.145 | 0.895 | 0.319 | 0/4 | True |
| USDJPY | session_range_fade | 2.0 | 2.5 | 48 | True | True | 0.065 |  | 376 | -38.811 | 0.849 | 0.356 | 1/4 | True |
| EURUSD | session_range_fade | 2.0 | 2.5 | 24 | True | True | 0.086 |  | 498 | -39.174 | 0.874 | 0.404 | 1/4 | True |
| EURUSD | session_range_fade | 2.5 | 2.5 | 48 | True | True | 0.086 |  | 409 | -40.879 | 0.866 | 0.337 | 2/4 | True |
| EURUSD | session_range_fade | 2.5 | 2.5 | 24 | True | True | 0.086 |  | 493 | -44.121 | 0.861 | 0.389 | 1/4 | True |
| USDJPY | session_range_fade | 1.5 | 2.5 | 48 | True | True | 0.065 |  | 400 | -44.509 | 0.825 | 0.403 | 1/4 | True |
| EURUSD | session_range_fade | 1.5 | 2.5 | 24 | True | True | 0.086 |  | 509 | -46.207 | 0.848 | 0.434 | 0/4 | True |
| USDJPY | session_range_fade | 2.5 | 2.5 | 24 | True | True | 0.065 |  | 456 | -48.667 | 0.822 | 0.382 | 0/4 | True |
| GBPUSD | session_range_fade | 2.5 | 2.5 | 96 | True | True | 0.074 |  | 386 | -54.056 | 0.827 | 0.295 | 1/4 | True |
| USDJPY | session_range_fade | 2.0 | 2.5 | 24 | True | True | 0.065 |  | 462 | -54.425 | 0.802 | 0.387 | 0/4 | True |
| USDJPY | session_range_fade | 2.0 | 2.0 | 48 | True | True | 0.082 |  | 438 | -54.878 | 0.828 | 0.342 | 1/4 | True |
| GBPUSD | session_range_fade | 2.0 | 2.5 | 96 | True | True | 0.074 |  | 425 | -56.643 | 0.824 | 0.339 | 1/4 | True |
| USDJPY | session_range_fade | 2.5 | 2.0 | 48 | True | True | 0.082 |  | 415 | -57.028 | 0.821 | 0.304 | 2/4 | True |

## Outputs

- `reports/research/fx_h1_session_range_relaxed_20260703/summary.csv`
- `reports/research/fx_h1_session_range_relaxed_20260703/coverage.csv`
- `reports/research/fx_h1_session_range_relaxed_20260703/trades.csv`
