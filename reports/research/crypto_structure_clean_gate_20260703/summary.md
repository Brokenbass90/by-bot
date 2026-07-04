# Structure break diagnostic

- market: `crypto`
- interval_min: `60`
- rows: 64
- coverage_gate: `True`
- cost_gate: `False`

| event | side | rr | sl_atr | hold | buffer | cd | cost | cost_skip | trades | netR | PF | WR | symbols+ | concentration | preflight |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| choch | short | 2.0 | 1.3 | 12 | 0.2 | 10 | True | 0 | 1104 | -74.342 | 0.890 | 0.396 | 4/12 | 9.33% | True |
| choch | short | 2.0 | 1.3 | 12 | 0.1 | 10 | True | 0 | 1213 | -74.483 | 0.898 | 0.404 | 3/12 | 9.32% | True |
| choch | short | 1.5 | 1.3 | 12 | 0.1 | 10 | True | 0 | 1218 | -76.237 | 0.890 | 0.443 | 2/12 | 9.28% | True |
| choch | short | 2.0 | 1.3 | 12 | 0.1 | 20 | True | 0 | 1102 | -77.894 | 0.885 | 0.403 | 3/12 | 9.44% | True |
| choch | short | 1.5 | 1.3 | 12 | 0.2 | 10 | True | 0 | 1109 | -78.086 | 0.878 | 0.435 | 2/12 | 9.29% | True |
| choch | short | 2.0 | 1.3 | 12 | 0.2 | 20 | True | 0 | 1008 | -78.255 | 0.875 | 0.396 | 4/12 | 9.33% | True |
| choch | short | 1.5 | 1.3 | 12 | 0.2 | 20 | True | 0 | 1015 | -78.609 | 0.868 | 0.436 | 3/12 | 9.26% | True |
| choch | short | 1.5 | 1.3 | 12 | 0.1 | 20 | True | 0 | 1109 | -79.413 | 0.876 | 0.442 | 2/12 | 9.38% | True |
| choch | short | 2.0 | 1.3 | 24 | 0.1 | 20 | True | 0 | 1075 | -83.114 | 0.888 | 0.373 | 2/12 | 9.40% | True |
| choch | short | 1.5 | 1.3 | 24 | 0.2 | 20 | True | 0 | 999 | -86.152 | 0.865 | 0.423 | 3/12 | 9.21% | True |
| choch | short | 1.5 | 1.3 | 24 | 0.1 | 20 | True | 0 | 1089 | -86.351 | 0.875 | 0.427 | 1/12 | 9.37% | True |
| choch | short | 2.0 | 1.3 | 24 | 0.1 | 10 | True | 0 | 1190 | -91.133 | 0.888 | 0.374 | 4/12 | 9.16% | True |
| choch | short | 2.0 | 1.3 | 24 | 0.2 | 20 | True | 0 | 980 | -91.485 | 0.866 | 0.368 | 3/12 | 9.29% | True |
| choch | short | 2.0 | 1.3 | 24 | 0.2 | 10 | True | 0 | 1084 | -91.920 | 0.877 | 0.373 | 3/12 | 9.23% | True |
| choch | short | 1.5 | 1.3 | 24 | 0.2 | 10 | True | 0 | 1094 | -92.400 | 0.867 | 0.425 | 2/12 | 9.23% | True |
| choch | short | 1.5 | 1.3 | 24 | 0.1 | 10 | True | 0 | 1200 | -95.893 | 0.873 | 0.427 | 2/12 | 9.17% | True |
| choch | short | 2.0 | 1.0 | 12 | 0.1 | 20 | True | 0 | 1120 | -111.716 | 0.856 | 0.385 | 3/12 | 9.38% | True |
| choch | short | 2.0 | 1.0 | 12 | 0.2 | 20 | True | 0 | 1025 | -118.625 | 0.836 | 0.378 | 3/12 | 9.27% | True |
| choch | short | 2.0 | 1.0 | 12 | 0.1 | 10 | True | 0 | 1228 | -121.885 | 0.856 | 0.384 | 3/12 | 9.36% | True |
| choch | short | 2.0 | 1.0 | 12 | 0.2 | 10 | True | 0 | 1118 | -122.922 | 0.843 | 0.378 | 2/12 | 9.39% | True |
| choch | short | 2.0 | 1.0 | 24 | 0.1 | 20 | True | 0 | 1104 | -125.455 | 0.847 | 0.359 | 2/12 | 9.33% | True |
| choch | short | 1.5 | 1.0 | 12 | 0.1 | 10 | True | 0 | 1241 | -128.411 | 0.838 | 0.433 | 3/12 | 9.43% | True |
| choch | short | 2.0 | 1.0 | 24 | 0.2 | 20 | True | 0 | 1011 | -130.785 | 0.828 | 0.353 | 3/12 | 9.20% | True |
| choch | short | 1.5 | 1.0 | 12 | 0.1 | 20 | True | 0 | 1130 | -130.821 | 0.822 | 0.430 | 2/12 | 9.38% | True |
| choch | short | 1.5 | 1.0 | 24 | 0.1 | 20 | True | 0 | 1123 | -134.916 | 0.822 | 0.424 | 2/12 | 9.35% | True |
| choch | short | 1.5 | 1.0 | 12 | 0.2 | 10 | True | 0 | 1127 | -142.661 | 0.806 | 0.423 | 2/12 | 9.41% | True |
| choch | short | 1.5 | 1.0 | 24 | 0.1 | 10 | True | 0 | 1234 | -143.484 | 0.827 | 0.425 | 2/12 | 9.32% | True |
| choch | short | 2.0 | 1.0 | 24 | 0.2 | 10 | True | 0 | 1106 | -144.768 | 0.825 | 0.353 | 2/12 | 9.40% | True |
| choch | short | 2.0 | 1.0 | 24 | 0.1 | 10 | True | 0 | 1212 | -148.592 | 0.836 | 0.356 | 3/12 | 9.24% | True |
| bos | short | 2.0 | 1.3 | 24 | 0.1 | 20 | True | 0 | 1935 | -272.135 | 0.804 | 0.345 | 1/12 | 8.94% | True |

## Outputs

- `reports/research/crypto_structure_clean_gate_20260703/summary.csv`
- `reports/research/crypto_structure_clean_gate_20260703/coverage.csv`
- `reports/research/crypto_structure_clean_gate_20260703/per_symbol.csv`
- `reports/research/crypto_structure_clean_gate_20260703/trades.csv`
