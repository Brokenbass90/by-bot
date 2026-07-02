# ATT1 short strict-OOS grading — 2026-07-02

Input:

- Source run: `backtest_runs/autoresearch_20260702_075058_att1_density_top_revalidate_20260626`
- Candidates: 12 ATT1 density revalidate configs.
- Side: `short` only.
- Method: filter each candidate's completed trades to `side=short`, split via `wf_folds.purge_embargo_folds(n_folds=4)`, grade through `oos_selector.evaluate_candidate`.
- Gates: `min_folds=4`, `min_frac_positive=0.75`, `min_trades_total=40`, `min_trades_per_fold=8`, `max_peak_ratio=3.0`, `min_robustness=0.0`.

Output:

- CSV: `backtest_runs/autoresearch_20260702_075058_att1_density_top_revalidate_20260626/att1_short_strict_oos_grading.csv`

Top result:

| run_id | pass | reason | short trades | robustness | median fold net | peak ratio | fold net R |
| ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | yes | robust_plateau | 239 | 3.498 | 6.149 | 2.354 | 5.6689 / 6.6301 / 1.8355 / 14.4745 |
| 7 | yes | robust_plateau | 239 | 3.498 | 6.149 | 2.354 | 5.6689 / 6.6301 / 1.8355 / 14.4745 |
| 5 | yes | robust_plateau | 244 | 2.521 | 5.272 | 2.931 | 4.3906 / 6.1526 / 3.4754 / 15.4497 |
| 11 | yes | robust_plateau | 244 | 2.521 | 5.272 | 2.931 | 4.3906 / 6.1526 / 3.4754 / 15.4497 |
| 3 | yes | robust_plateau | 244 | 2.332 | 5.096 | 2.986 | 3.5797 / 6.6115 / 3.4645 / 15.2160 |
| 9 | yes | robust_plateau | 244 | 2.332 | 5.096 | 2.986 | 3.5797 / 6.6115 / 3.4645 / 15.2160 |

Verdict:

- 6/12 ATT1-short candidates pass the strict fold grading.
- Best candidates are not single-window heroes under this grading: all 4 folds are positive and `peak_ratio < 3`.
- This strengthens the case that `ATT1 short-only` is the first crypto sleeve to promote from tiny canary if live health stays clean.

Limitations:

- This is strict grading of fixed candidates from the completed revalidate run.
- It is not yet a full rolling train/test re-selection harness.
- Before raising risk materially, run one final fee/slippage stress and/or true rolling train/test selection if time permits.

Operational implication:

- Keep current live `ATT1 short` tiny canary active.
- If no live degradation and fee-stress does not break the result, next controlled step is `risk_mult`/base-risk increase via `smart_risk`, not manual fixed boost.
- `ATT1 long` remains out of live promotion path.
