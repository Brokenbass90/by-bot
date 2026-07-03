# Structure break diagnostic

- market: `crypto`
- interval_min: `60`
- rows: 4

| event | side | rr | sl_atr | hold | buffer | trades | netR | PF | WR | symbols | preflight |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| choch | long | 1.5 | 1.0 | 12 | 0.1 | 241 | -57.074 | 0.662 | 0.394 | 4 | False |
| choch | short | 1.5 | 1.0 | 12 | 0.1 | 261 | -99.615 | 0.514 | 0.330 | 4 | False |
| bos | short | 1.5 | 1.0 | 12 | 0.1 | 717 | -134.614 | 0.725 | 0.402 | 4 | False |
| bos | long | 1.5 | 1.0 | 12 | 0.1 | 691 | -234.641 | 0.558 | 0.356 | 4 | False |

## Outputs

- `reports/research/structure_break_crypto_smoke_20260702/summary.csv`
- `reports/research/structure_break_crypto_smoke_20260702/trades.csv`
