# Structure break diagnostic

- market: `fx`
- interval_min: `60`
- rows: 96

| event | side | rr | sl_atr | hold | buffer | trades | netR | PF | WR | symbols | preflight |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| choch | short | 1.5 | 1.0 | 6 | 0.2 | 81 | -0.856 | 0.980 | 0.494 | 4 | True |
| choch | short | 1.5 | 1.0 | 6 | 0.1 | 85 | -3.449 | 0.923 | 0.482 | 4 | True |
| choch | short | 2.0 | 0.8 | 12 | 0.2 | 76 | -4.094 | 0.929 | 0.447 | 4 | True |
| choch | short | 2.0 | 1.0 | 12 | 0.2 | 72 | -4.633 | 0.908 | 0.417 | 4 | True |
| choch | short | 2.0 | 0.8 | 6 | 0.2 | 78 | -4.796 | 0.908 | 0.449 | 4 | True |
| choch | short | 1.0 | 1.0 | 6 | 0.2 | 87 | -5.153 | 0.865 | 0.575 | 4 | True |
| choch | short | 2.0 | 1.0 | 6 | 0.2 | 75 | -5.179 | 0.881 | 0.427 | 4 | True |
| choch | short | 1.5 | 1.0 | 12 | 0.2 | 79 | -5.239 | 0.897 | 0.494 | 4 | True |
| choch | short | 1.0 | 1.0 | 6 | 0.1 | 91 | -5.986 | 0.847 | 0.571 | 4 | True |
| choch | short | 2.0 | 1.0 | 6 | 0.1 | 80 | -6.480 | 0.861 | 0.425 | 4 | True |
| choch | short | 1.5 | 0.8 | 12 | 0.2 | 84 | -6.862 | 0.877 | 0.512 | 4 | True |
| choch | short | 1.5 | 0.8 | 6 | 0.2 | 86 | -7.134 | 0.863 | 0.512 | 4 | True |
| choch | short | 2.0 | 1.0 | 12 | 0.1 | 77 | -7.987 | 0.855 | 0.403 | 4 | True |
| choch | short | 1.0 | 1.0 | 12 | 0.2 | 86 | -8.155 | 0.816 | 0.593 | 4 | True |
| choch | short | 2.0 | 0.8 | 6 | 0.1 | 82 | -8.595 | 0.845 | 0.439 | 4 | True |
| choch | short | 2.0 | 0.8 | 12 | 0.1 | 80 | -9.384 | 0.851 | 0.425 | 4 | True |
| choch | short | 1.5 | 1.0 | 12 | 0.1 | 83 | -10.271 | 0.817 | 0.470 | 4 | True |
| choch | short | 1.5 | 0.8 | 12 | 0.1 | 88 | -12.136 | 0.802 | 0.489 | 4 | True |
| choch | short | 1.0 | 1.0 | 12 | 0.1 | 90 | -11.174 | 0.766 | 0.578 | 4 | False |
| choch | short | 1.5 | 0.8 | 6 | 0.1 | 90 | -11.233 | 0.800 | 0.500 | 4 | False |
| choch | short | 1.0 | 0.8 | 6 | 0.2 | 87 | -14.645 | 0.671 | 0.575 | 4 | False |
| choch | short | 1.0 | 0.8 | 12 | 0.2 | 85 | -17.663 | 0.632 | 0.577 | 4 | False |
| choch | short | 1.0 | 0.8 | 6 | 0.1 | 95 | -18.547 | 0.634 | 0.558 | 4 | False |
| choch | short | 1.0 | 0.8 | 12 | 0.1 | 93 | -22.407 | 0.593 | 0.559 | 4 | False |
| choch | long | 2.0 | 1.0 | 12 | 0.2 | 74 | -26.980 | 0.569 | 0.311 | 4 | False |
| choch | long | 2.0 | 1.0 | 6 | 0.2 | 75 | -28.020 | 0.517 | 0.307 | 4 | False |
| choch | long | 2.0 | 1.0 | 12 | 0.1 | 81 | -29.541 | 0.563 | 0.321 | 4 | False |
| choch | long | 2.0 | 1.0 | 6 | 0.1 | 82 | -29.811 | 0.519 | 0.317 | 4 | False |
| choch | long | 1.5 | 1.0 | 12 | 0.1 | 83 | -39.413 | 0.438 | 0.337 | 4 | False |
| choch | long | 1.5 | 1.0 | 12 | 0.2 | 76 | -39.448 | 0.404 | 0.316 | 4 | False |

## Outputs

- `reports/research/structure_break_fx_overnight_20260702/summary.csv`
- `reports/research/structure_break_fx_overnight_20260702/trades.csv`
