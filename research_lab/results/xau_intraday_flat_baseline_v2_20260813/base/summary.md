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
| XAUUSD | session_breakout_retest | 2.0 | 1.5 | 6 | True | True | 0.053 |  | 13 | 3.915 | 1.730 | 0.615 | 3/4 | False |
| XAUUSD | round_level_sweep | 2.0 | 1.5 | 6 | True | True | 0.053 |  | 17 | -2.421 | 0.701 | 0.412 | 2/4 | False |
| XAUUSD | trend_pullback | 2.0 | 1.5 | 6 | True | True | 0.053 |  | 18 | -3.692 | 0.595 | 0.389 | 1/4 | False |

## Outputs

- `research_lab/results/xau_intraday_flat_baseline_v2_20260813/base/summary.csv`
- `research_lab/results/xau_intraday_flat_baseline_v2_20260813/base/coverage.csv`
- `research_lab/results/xau_intraday_flat_baseline_v2_20260813/base/trades.csv`
