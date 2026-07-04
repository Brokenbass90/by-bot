# FX native harness summary

- rows: 81
- data_dir: `data_cache/forex_1h`
- interval_min: `60`
- coverage_gate: `True`
- cost_gate: `True`

| symbol | setup | rr | sl_atr | hold | coverage | cost | feeR | skip | trades | netR | PF | WR | folds+ | preflight |
|---|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|
| EURUSD | round_level_sweep | 2.5 | 1.6 | 48 | True | True | 0.135 |  | 3 | 6.877 | inf | 1.000 | 3/4 | False |
| EURUSD | round_level_sweep | 2.5 | 1.6 | 96 | True | True | 0.135 |  | 3 | 6.877 | inf | 1.000 | 3/4 | False |
| EURUSD | round_level_sweep | 2.5 | 1.6 | 168 | True | True | 0.135 |  | 3 | 6.877 | inf | 1.000 | 3/4 | False |
| EURUSD | round_level_sweep | 2.5 | 1.3 | 48 | True | True | 0.166 |  | 3 | 6.733 | inf | 1.000 | 3/4 | False |
| EURUSD | round_level_sweep | 2.5 | 1.3 | 96 | True | True | 0.166 |  | 3 | 6.733 | inf | 1.000 | 3/4 | False |
| EURUSD | round_level_sweep | 2.5 | 1.3 | 168 | True | True | 0.166 |  | 3 | 6.733 | inf | 1.000 | 3/4 | False |
| EURUSD | round_level_sweep | 2.5 | 1.0 | 48 | True | True | 0.216 |  | 3 | 6.503 | inf | 1.000 | 3/4 | False |
| EURUSD | round_level_sweep | 2.5 | 1.0 | 96 | True | True | 0.216 |  | 3 | 6.503 | inf | 1.000 | 3/4 | False |
| EURUSD | round_level_sweep | 2.5 | 1.0 | 168 | True | True | 0.216 |  | 3 | 6.503 | inf | 1.000 | 3/4 | False |
| USDJPY | round_level_sweep | 2.5 | 1.0 | 48 | True | True | 0.163 |  | 30 | 5.976 | 1.265 | 0.433 | 3/4 | False |
| USDJPY | round_level_sweep | 2.5 | 1.0 | 96 | True | True | 0.163 |  | 30 | 5.976 | 1.265 | 0.433 | 3/4 | False |
| USDJPY | round_level_sweep | 2.5 | 1.0 | 168 | True | True | 0.163 |  | 30 | 5.976 | 1.265 | 0.433 | 3/4 | False |
| USDJPY | round_level_sweep | 2.0 | 1.0 | 48 | True | True | 0.163 |  | 30 | 5.476 | 1.277 | 0.500 | 2/4 | False |
| USDJPY | round_level_sweep | 2.0 | 1.0 | 96 | True | True | 0.163 |  | 30 | 5.476 | 1.277 | 0.500 | 2/4 | False |
| USDJPY | round_level_sweep | 2.0 | 1.0 | 168 | True | True | 0.163 |  | 30 | 5.476 | 1.277 | 0.500 | 2/4 | False |
| EURUSD | round_level_sweep | 2.0 | 1.6 | 48 | True | True | 0.135 |  | 3 | 5.377 | inf | 1.000 | 3/4 | False |
| EURUSD | round_level_sweep | 2.0 | 1.6 | 96 | True | True | 0.135 |  | 3 | 5.377 | inf | 1.000 | 3/4 | False |
| EURUSD | round_level_sweep | 2.0 | 1.6 | 168 | True | True | 0.135 |  | 3 | 5.377 | inf | 1.000 | 3/4 | False |
| EURUSD | round_level_sweep | 2.0 | 1.3 | 48 | True | True | 0.166 |  | 3 | 5.233 | inf | 1.000 | 3/4 | False |
| EURUSD | round_level_sweep | 2.0 | 1.3 | 96 | True | True | 0.166 |  | 3 | 5.233 | inf | 1.000 | 3/4 | False |

## Outputs

- `reports/research/fx_h1_round_sweep_20260704_fast/summary.csv`
- `reports/research/fx_h1_round_sweep_20260704_fast/coverage.csv`
- `reports/research/fx_h1_round_sweep_20260704_fast/trades.csv`
