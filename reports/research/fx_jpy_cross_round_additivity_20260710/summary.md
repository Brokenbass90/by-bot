# JPY-cross round-level additivity

- verdict: **FAIL_ADDITIVITY**
- fixed RR/SL/hold: `2.5 / 1.0 ATR / 120 H1 bars`
- base/stress costs: `3 / 5 bps` round trip

| pair | mode | side | cost | segment | N | netR | PF | WR |
|---|---|---|---|---|---:|---:|---:|---:|
| EURJPY | standard_00_50 | short | base | validation | 37 | -23.867 | 0.388 | 0.189 |
| EURJPY | standard_00_50 | short | base | holdout | 55 | -21.218 | 0.604 | 0.273 |
| EURJPY | standard_00_50 | short | base | full | 170 | -46.177 | 0.700 | 0.282 |
| EURJPY | standard_00_50 | short | stress | validation | 37 | -31.445 | 0.301 | 0.189 |
| EURJPY | standard_00_50 | short | stress | holdout | 55 | -33.698 | 0.461 | 0.273 |
| EURJPY | standard_00_50 | short | stress | full | 170 | -75.629 | 0.569 | 0.282 |
| EURJPY | standard_00_50 | long | base | validation | 47 | -7.173 | 0.824 | 0.319 |
| EURJPY | standard_00_50 | long | base | holdout | 32 | -0.047 | 0.998 | 0.375 |
| EURJPY | standard_00_50 | long | base | full | 152 | -22.061 | 0.828 | 0.309 |
| EURJPY | standard_00_50 | long | stress | validation | 47 | -15.621 | 0.665 | 0.319 |
| EURJPY | standard_00_50 | long | stress | holdout | 32 | -6.745 | 0.774 | 0.375 |
| EURJPY | standard_00_50 | long | stress | full | 152 | -45.102 | 0.687 | 0.309 |
| EURJPY | big_figure_00 | short | base | validation | 18 | -9.254 | 0.488 | 0.222 |
| EURJPY | big_figure_00 | short | base | holdout | 29 | -18.187 | 0.410 | 0.207 |
| EURJPY | big_figure_00 | short | base | full | 84 | -22.340 | 0.708 | 0.286 |
| EURJPY | big_figure_00 | short | stress | validation | 18 | -12.757 | 0.387 | 0.222 |
| EURJPY | big_figure_00 | short | stress | holdout | 29 | -24.979 | 0.306 | 0.207 |
| EURJPY | big_figure_00 | short | stress | full | 84 | -37.233 | 0.573 | 0.286 |
| EURJPY | big_figure_00 | long | base | validation | 24 | -2.696 | 0.868 | 0.333 |
| EURJPY | big_figure_00 | long | base | holdout | 16 | -0.163 | 0.988 | 0.375 |
| EURJPY | big_figure_00 | long | base | full | 73 | 0.815 | 1.014 | 0.356 |
| EURJPY | big_figure_00 | long | stress | validation | 24 | -7.160 | 0.695 | 0.333 |
| EURJPY | big_figure_00 | long | stress | holdout | 16 | -3.606 | 0.765 | 0.375 |
| EURJPY | big_figure_00 | long | stress | full | 73 | -10.641 | 0.837 | 0.356 |
| GBPJPY | standard_00_50 | short | base | validation | 50 | -14.015 | 0.691 | 0.280 |
| GBPJPY | standard_00_50 | short | base | holdout | 60 | -35.465 | 0.431 | 0.200 |
| GBPJPY | standard_00_50 | short | base | full | 199 | -62.561 | 0.655 | 0.261 |
| GBPJPY | standard_00_50 | short | stress | validation | 50 | -22.692 | 0.559 | 0.280 |
| GBPJPY | standard_00_50 | short | stress | holdout | 60 | -47.108 | 0.345 | 0.200 |
| GBPJPY | standard_00_50 | short | stress | full | 199 | -92.934 | 0.545 | 0.261 |
| GBPJPY | standard_00_50 | long | base | validation | 41 | -5.502 | 0.842 | 0.317 |
| GBPJPY | standard_00_50 | long | base | holdout | 45 | -15.371 | 0.633 | 0.267 |
| GBPJPY | standard_00_50 | long | base | full | 197 | -26.889 | 0.837 | 0.305 |
| GBPJPY | standard_00_50 | long | stress | validation | 41 | -12.170 | 0.690 | 0.317 |
| GBPJPY | standard_00_50 | long | stress | holdout | 45 | -23.618 | 0.506 | 0.267 |
| GBPJPY | standard_00_50 | long | stress | full | 197 | -53.481 | 0.709 | 0.305 |
| GBPJPY | big_figure_00 | short | base | validation | 25 | -10.377 | 0.568 | 0.240 |
| GBPJPY | big_figure_00 | short | base | holdout | 32 | -27.125 | 0.251 | 0.125 |
| GBPJPY | big_figure_00 | short | base | full | 103 | -45.721 | 0.537 | 0.223 |
| GBPJPY | big_figure_00 | short | stress | validation | 25 | -14.628 | 0.465 | 0.240 |
| GBPJPY | big_figure_00 | short | stress | holdout | 32 | -33.208 | 0.204 | 0.125 |
| GBPJPY | big_figure_00 | short | stress | full | 103 | -61.202 | 0.450 | 0.223 |
| GBPJPY | big_figure_00 | long | base | validation | 21 | -5.468 | 0.707 | 0.286 |
| GBPJPY | big_figure_00 | long | base | holdout | 22 | -13.787 | 0.394 | 0.182 |
| GBPJPY | big_figure_00 | long | base | full | 105 | -21.406 | 0.764 | 0.286 |
| GBPJPY | big_figure_00 | long | stress | validation | 21 | -9.114 | 0.569 | 0.286 |
| GBPJPY | big_figure_00 | long | stress | holdout | 22 | -17.646 | 0.319 | 0.182 |
| GBPJPY | big_figure_00 | long | stress | full | 105 | -35.676 | 0.648 | 0.286 |

## Checks

- `EURJPY_full_stress_n_ge_30`: `True`
- `EURJPY_full_stress_pf_ge_1_05`: `False`
- `EURJPY_validation_stress_positive`: `False`
- `EURJPY_holdout_stress_n_ge_5`: `True`
- `EURJPY_holdout_stress_pf_ge_1_10`: `False`
- `GBPJPY_full_stress_n_ge_30`: `True`
- `GBPJPY_full_stress_pf_ge_1_05`: `False`
- `GBPJPY_validation_stress_positive`: `False`
- `GBPJPY_holdout_stress_n_ge_5`: `True`
- `GBPJPY_holdout_stress_pf_ge_1_10`: `False`
