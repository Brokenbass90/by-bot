# InPlay V4 mechanics gate — FAIL

- symbols: `ADAUSDT,DOGEUSDT,SUIUSDT`
- folds: `2` rolling train/test
- train_days: `60`
- test_days: `30`
- grid_combos_per_fold: `1`
- OOS total trades: `3`
- OOS total net: `-0.06R`
- oos_selector: `passes=False`, reason `thin_fold_0`, robustness `-0.051`
- raw runs: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/reports/research/irv4_mechanics_gate_smoke2_20260701_20260701_093254/runs.csv`

## Selected params by fold

- fold 1: score `-1000000000.000000` — IRV4_TP_RR=2.0, IRV4_RETEST_MIN_QUALITY=0.35, IRV4_LEVEL_ENTRY_VALIDITY_BARS=2, IRV4_LEVEL_ENTRY_MAX_CHASE_ATR=0.4
- fold 2: score `-1000000000.000000` — IRV4_TP_RR=2.0, IRV4_RETEST_MIN_QUALITY=0.35, IRV4_LEVEL_ENTRY_VALIDITY_BARS=2, IRV4_LEVEL_ENTRY_MAX_CHASE_ATR=0.4

## OOS rows

- fold 1: trades `0`, net `0.00`, PF `0.000`, DD `0.0000`, tag `irv4_mechanics_gate_smoke2_20260701_f01_oos_20260701_093254`
- fold 2: trades `3`, net `-0.06`, PF `0.824`, DD `0.3355`, tag `irv4_mechanics_gate_smoke2_20260701_f02_oos_20260701_093254`
