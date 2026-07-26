# FX native harness summary

- rows: 360
- data_dir: `data_cache/forex`
- interval_min: `60`
- coverage_gate: `True`
- cost_gate: `True`

| symbol | setup | rr | sl_atr | hold | coverage | cost | feeR | skip | trades | netR | PF | WR | folds+ | preflight |
|---|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|
| EURUSD | session_range_fade | 1.5 | 0.8 | 24 | True | False | 1.220 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 1.5 | 0.8 | 72 | True | False | 1.220 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 1.5 | 1.0 | 24 | True | False | 0.976 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 1.5 | 1.0 | 72 | True | False | 0.976 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 1.5 | 1.3 | 24 | True | False | 0.751 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 1.5 | 1.3 | 72 | True | False | 0.751 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 2.0 | 0.8 | 24 | True | False | 1.220 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 2.0 | 0.8 | 72 | True | False | 1.220 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 2.0 | 1.0 | 24 | True | False | 0.976 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 2.0 | 1.0 | 72 | True | False | 0.976 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 2.0 | 1.3 | 24 | True | False | 0.751 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 2.0 | 1.3 | 72 | True | False | 0.751 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 2.5 | 0.8 | 24 | True | False | 1.220 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 2.5 | 0.8 | 72 | True | False | 1.220 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 2.5 | 1.0 | 24 | True | False | 0.976 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 2.5 | 1.0 | 72 | True | False | 0.976 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 2.5 | 1.3 | 24 | True | False | 0.751 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | session_range_fade | 2.5 | 1.3 | 72 | True | False | 0.751 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | round_level_sweep | 1.5 | 0.8 | 24 | True | False | 1.220 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| EURUSD | round_level_sweep | 1.5 | 0.8 | 72 | True | False | 1.220 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |

## Outputs

- `reports/research/fx_income_h1_diag_stress_20260726/summary.csv`
- `reports/research/fx_income_h1_diag_stress_20260726/coverage.csv`
- `reports/research/fx_income_h1_diag_stress_20260726/trades.csv`
