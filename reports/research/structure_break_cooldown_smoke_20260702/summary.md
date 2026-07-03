# Structure break diagnostic

- market: `crypto`
- interval_min: `60`
- rows: 4

| event | side | rr | sl_atr | hold | buffer | cd | trades | netR | PF | WR | symbols+ | concentration | preflight |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| bos | short | 1.5 | 1.0 | 6 | 0.1 | 10 | 69 | -12.351 | 0.709 | 0.435 | 0/2 | 50.72% | False |
| bos | long | 1.5 | 1.0 | 6 | 0.1 | 10 | 61 | -16.504 | 0.599 | 0.377 | 0/2 | 54.10% | False |
| bos | short | 1.5 | 1.0 | 6 | 0.1 | 0 | 127 | -21.949 | 0.719 | 0.441 | 0/2 | 51.97% | False |
| bos | long | 1.5 | 1.0 | 6 | 0.1 | 0 | 106 | -37.302 | 0.517 | 0.358 | 0/2 | 52.83% | False |

## Outputs

- `reports/research/structure_break_cooldown_smoke_20260702/summary.csv`
- `reports/research/structure_break_cooldown_smoke_20260702/per_symbol.csv`
- `reports/research/structure_break_cooldown_smoke_20260702/trades.csv`
