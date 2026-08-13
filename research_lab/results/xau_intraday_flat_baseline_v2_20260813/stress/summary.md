# FX native harness summary

- rows: 3
- data_dir: `research_lab/data/xauusd_m5_preholdout_20240708_20250930_v2`
- interval_min: `60`
- requested_window_utc: `2024-07-08..2025-10-01` (end exclusive)
- coverage_gate: `True`
- cost_gate: `True`
- force_flat_utc: `20:55`

| symbol | setup | rr | sl_atr | hold | coverage | cost | feeR | skip | trades | netR | PF | WR | folds+ | preflight |
|---|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|
| XAUUSD | session_breakout_retest | 2.0 | 1.5 | 6 | True | True | 0.105 |  | 13 | 3.012 | 1.526 | 0.615 | 3/4 | False |
| XAUUSD | round_level_sweep | 2.0 | 1.5 | 6 | True | True | 0.105 |  | 17 | -3.822 | 0.576 | 0.412 | 1/4 | False |
| XAUUSD | trend_pullback | 2.0 | 1.5 | 6 | True | True | 0.105 |  | 18 | -5.231 | 0.482 | 0.333 | 0/4 | False |

## Outputs

- `research_lab/results/xau_intraday_flat_baseline_v2_20260813/stress/summary.csv`
- `research_lab/results/xau_intraday_flat_baseline_v2_20260813/stress/coverage.csv`
- `research_lab/results/xau_intraday_flat_baseline_v2_20260813/stress/trades.csv`
