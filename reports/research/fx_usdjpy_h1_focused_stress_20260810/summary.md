# FX native harness summary

- rows: 8
- data_dir: `data_cache/forex`
- interval_min: `60`
- coverage_gate: `True`
- cost_gate: `True`

| symbol | setup | rr | sl_atr | hold | coverage | cost | feeR | skip | trades | netR | PF | WR | folds+ | preflight |
|---|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|
| USDJPY | session_breakout_retest | 1.5 | 1.3 | 24 | True | False | 0.515 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| USDJPY | session_breakout_retest | 1.5 | 1.3 | 72 | True | False | 0.515 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| USDJPY | session_breakout_retest | 2.5 | 1.3 | 24 | True | False | 0.515 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| USDJPY | session_breakout_retest | 2.5 | 1.3 | 72 | True | False | 0.515 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| USDJPY | round_level_sweep | 1.5 | 1.3 | 24 | True | False | 0.515 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| USDJPY | round_level_sweep | 1.5 | 1.3 | 72 | True | False | 0.515 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| USDJPY | round_level_sweep | 2.5 | 1.3 | 24 | True | False | 0.515 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |
| USDJPY | round_level_sweep | 2.5 | 1.3 | 72 | True | False | 0.515 | cost_infeasible | 0 | 0.000 | 0.000 | 0.000 | 0/4 | False |

## Outputs

- `reports/research/fx_usdjpy_h1_focused_stress_20260810/summary.csv`
- `reports/research/fx_usdjpy_h1_focused_stress_20260810/coverage.csv`
- `reports/research/fx_usdjpy_h1_focused_stress_20260810/trades.csv`
