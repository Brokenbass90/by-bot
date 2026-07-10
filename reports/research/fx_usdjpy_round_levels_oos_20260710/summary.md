# USDJPY 00/50 vs big-figure vs legacy-decade OOS

- bars: `12341`; coverage: `0.988625`
- verdict: **NO_PROMOTION** (never direct demo/live promotion)
- frozen RR/SL/hold: `2.5 / 1.0 ATR / 120 H1 bars`
- costs: base `3 bps` round trip; stress `5 bps` round trip

| mode | side | cost | segment | N | netR | PF | WR | folds+ |
|---|---|---|---|---:|---:|---:|---:|---:|
| standard_00_50 | short | base | validation | 58 | -22.629 | 0.583 | 0.241 | 2/4 |
| standard_00_50 | short | base | holdout | 49 | -7.693 | 0.824 | 0.347 | 2/4 |
| standard_00_50 | short | base | full | 190 | -5.677 | 0.963 | 0.347 | 2/4 |
| standard_00_50 | short | stress | validation | 58 | -31.715 | 0.480 | 0.241 | 2/4 |
| standard_00_50 | short | stress | holdout | 49 | -19.822 | 0.615 | 0.347 | 2/4 |
| standard_00_50 | short | stress | full | 190 | -36.796 | 0.789 | 0.347 | 2/4 |
| standard_00_50 | long | base | validation | 37 | -35.882 | 0.156 | 0.081 | 1/4 |
| standard_00_50 | long | base | holdout | 23 | 10.259 | 1.693 | 0.478 | 1/4 |
| standard_00_50 | long | base | full | 146 | -41.102 | 0.682 | 0.260 | 1/4 |
| standard_00_50 | long | stress | validation | 37 | -42.138 | 0.126 | 0.081 | 1/4 |
| standard_00_50 | long | stress | holdout | 23 | 6.765 | 1.405 | 0.478 | 1/4 |
| standard_00_50 | long | stress | full | 146 | -59.837 | 0.582 | 0.260 | 1/4 |
| big_figure_00 | short | base | validation | 34 | -4.125 | 0.857 | 0.324 | 3/4 |
| big_figure_00 | short | base | holdout | 23 | 0.314 | 1.017 | 0.391 | 3/4 |
| big_figure_00 | short | base | full | 108 | 26.883 | 1.349 | 0.426 | 3/4 |
| big_figure_00 | short | stress | validation | 34 | -9.874 | 0.698 | 0.324 | 2/4 |
| big_figure_00 | short | stress | holdout | 23 | -5.144 | 0.764 | 0.391 | 2/4 |
| big_figure_00 | short | stress | full | 108 | 9.471 | 1.109 | 0.426 | 2/4 |
| big_figure_00 | long | base | validation | 19 | -16.661 | 0.208 | 0.105 | 1/4 |
| big_figure_00 | long | base | holdout | 12 | -4.433 | 0.605 | 0.250 | 1/4 |
| big_figure_00 | long | base | full | 78 | -29.623 | 0.585 | 0.231 | 1/4 |
| big_figure_00 | long | stress | validation | 19 | -19.768 | 0.167 | 0.105 | 1/4 |
| big_figure_00 | long | stress | holdout | 12 | -6.388 | 0.498 | 0.250 | 1/4 |
| big_figure_00 | long | stress | full | 78 | -39.371 | 0.501 | 0.231 | 1/4 |
| legacy_decade | short | base | validation | 2 | 1.119 | 1.976 | 0.500 | 3/4 |
| legacy_decade | short | base | holdout | 5 | 6.496 | 4.546 | 0.800 | 3/4 |
| legacy_decade | short | base | full | 12 | 8.512 | 2.306 | 0.583 | 3/4 |
| legacy_decade | short | stress | validation | 2 | 0.865 | 1.695 | 0.500 | 3/4 |
| legacy_decade | short | stress | holdout | 5 | 4.827 | 3.022 | 0.800 | 3/4 |
| legacy_decade | short | stress | full | 12 | 5.854 | 1.777 | 0.583 | 3/4 |
| legacy_decade | long | base | validation | 0 | 0.000 | 0.000 | 0.000 | 1/4 |
| legacy_decade | long | base | holdout | 1 | -1.442 | 0.000 | 0.000 | 1/4 |
| legacy_decade | long | base | full | 5 | -2.477 | 0.485 | 0.200 | 1/4 |
| legacy_decade | long | stress | validation | 0 | 0.000 | 0.000 | 0.000 | 1/4 |
| legacy_decade | long | stress | holdout | 1 | -1.737 | 0.000 | 0.000 | 1/4 |
| legacy_decade | long | stress | full | 5 | -3.128 | 0.415 | 0.200 | 1/4 |

## Gate checks

- `full_base_n_ge_30`: `True`
- `full_base_pf_ge_1_15`: `False`
- `full_stress_pf_ge_1_05`: `False`
- `stress_positive_folds_ge_3`: `False`
- `validation_stress_n_ge_5`: `True`
- `validation_stress_net_positive`: `False`
- `holdout_stress_n_ge_5`: `True`
- `holdout_stress_pf_ge_1_10`: `False`
- `holdout_stress_net_positive`: `False`

Legacy decade results are replay-only because that family was selected on already-seen history.
A primary PASS only authorizes an independent-feed replay, then demo shadow after execution/news gates.
