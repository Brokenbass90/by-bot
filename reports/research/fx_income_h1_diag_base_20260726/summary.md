# FX native harness summary

- rows: 360
- data_dir: `data_cache/forex`
- interval_min: `60`
- coverage_gate: `True`
- cost_gate: `True`

| symbol | setup | rr | sl_atr | hold | coverage | cost | feeR | skip | trades | netR | PF | WR | folds+ | preflight |
|---|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|
| USDJPY | session_breakout_retest | 1.5 | 1.3 | 24 | True | True | 0.247 |  | 30 | 2.494 | 1.148 | 0.500 | 2/4 | True |
| USDJPY | session_breakout_retest | 1.5 | 1.3 | 72 | True | True | 0.247 |  | 30 | 1.117 | 1.062 | 0.467 | 2/4 | True |
| USDJPY | session_range_fade | 2.0 | 1.3 | 72 | True | True | 0.247 |  | 445 | -37.659 | 0.886 | 0.357 | 2/4 | True |
| USDJPY | session_range_fade | 2.0 | 1.3 | 24 | True | True | 0.247 |  | 458 | -51.597 | 0.848 | 0.354 | 0/4 | True |
| USDJPY | session_range_fade | 2.5 | 1.3 | 72 | True | True | 0.247 |  | 400 | -60.662 | 0.816 | 0.287 | 1/4 | True |
| USDJPY | session_breakout_retest | 2.5 | 1.3 | 24 | True | True | 0.247 |  | 29 | 4.078 | 1.214 | 0.414 | 3/4 | False |
| USDJPY | round_level_sweep | 2.0 | 1.3 | 24 | True | True | 0.247 |  | 17 | 3.945 | 1.378 | 0.471 | 3/4 | False |
| USDJPY | round_level_sweep | 2.0 | 1.3 | 72 | True | True | 0.247 |  | 17 | 3.945 | 1.378 | 0.471 | 3/4 | False |
| USDJPY | session_breakout_retest | 2.0 | 1.3 | 24 | True | True | 0.247 |  | 29 | 2.578 | 1.144 | 0.448 | 3/4 | False |
| USDJPY | round_level_sweep | 1.5 | 1.3 | 24 | True | True | 0.247 |  | 17 | 2.445 | 1.263 | 0.529 | 3/4 | False |
| USDJPY | round_level_sweep | 1.5 | 1.3 | 72 | True | True | 0.247 |  | 17 | 2.445 | 1.263 | 0.529 | 3/4 | False |
| USDJPY | round_level_sweep | 2.5 | 1.3 | 72 | True | True | 0.247 |  | 16 | 2.375 | 1.204 | 0.375 | 2/4 | False |
| USDJPY | session_breakout_retest | 2.5 | 1.3 | 72 | True | True | 0.247 |  | 29 | 2.259 | 1.106 | 0.345 | 3/4 | False |
| USDJPY | round_level_sweep | 2.5 | 1.3 | 24 | True | True | 0.247 |  | 17 | 1.383 | 1.115 | 0.353 | 2/4 | False |
| USDJPY | session_breakout_retest | 2.0 | 1.3 | 72 | True | True | 0.247 |  | 29 | 0.259 | 1.013 | 0.379 | 2/4 | False |
| EURUSD | session_range_fade | 1.5 | 0.8 | 24 | True | False | 0.586 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 1.5 | 0.8 | 72 | True | False | 0.586 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 1.5 | 1.0 | 24 | True | False | 0.468 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 1.5 | 1.0 | 72 | True | False | 0.468 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 1.5 | 1.3 | 24 | True | False | 0.360 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |

## Outputs

- `reports/research/fx_income_h1_diag_base_20260726/summary.csv`
- `reports/research/fx_income_h1_diag_base_20260726/coverage.csv`
- `reports/research/fx_income_h1_diag_base_20260726/trades.csv`
