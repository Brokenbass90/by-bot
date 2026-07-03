# InPlay V4 mechanics gate — FAIL

- symbols: `ADAUSDT,DOGEUSDT,SUIUSDT`
- folds: `4` rolling train/test
- train_days: `120`
- test_days: `60`
- grid_combos_per_fold: `36`
- OOS total trades: `21`
- OOS total net: `0.96R`
- oos_selector: `passes=False`, reason `unstable_frac_pos_0.50`, robustness `0.060`
- raw runs: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/reports/research/irv4_mechanics_gate_full_ada_doge_sui_20260701_20260701_104508/runs.csv`

## Selected params by fold

- fold 1: score `12.028875` — IRV4_TP_RR=2.0, IRV4_RETEST_MIN_QUALITY=0.35, IRV4_LEVEL_ENTRY_VALIDITY_BARS=2, IRV4_LEVEL_ENTRY_MAX_CHASE_ATR=0.4
- fold 2: score `8.181500` — IRV4_TP_RR=2.5, IRV4_RETEST_MIN_QUALITY=0.45, IRV4_LEVEL_ENTRY_VALIDITY_BARS=2, IRV4_LEVEL_ENTRY_MAX_CHASE_ATR=0.4
- fold 3: score `13.938750` — IRV4_TP_RR=3.0, IRV4_RETEST_MIN_QUALITY=0.45, IRV4_LEVEL_ENTRY_VALIDITY_BARS=4, IRV4_LEVEL_ENTRY_MAX_CHASE_ATR=0.4
- fold 4: score `8.247625` — IRV4_TP_RR=3.0, IRV4_RETEST_MIN_QUALITY=0.35, IRV4_LEVEL_ENTRY_VALIDITY_BARS=4, IRV4_LEVEL_ENTRY_MAX_CHASE_ATR=0.4

## OOS rows

- fold 1: trades `9`, net `0.62`, PF `1.620`, DD `0.9975`, tag `irv4_mechanics_gate_full_ada_doge_sui_20260701_f01_oos_20260701_104508`
- fold 2: trades `6`, net `0.64`, PF `2.208`, DD `0.2847`, tag `irv4_mechanics_gate_full_ada_doge_sui_20260701_f02_oos_20260701_104508`
- fold 3: trades `1`, net `-0.26`, PF `0.000`, DD `0.2578`, tag `irv4_mechanics_gate_full_ada_doge_sui_20260701_f03_oos_20260701_104508`
- fold 4: trades `5`, net `-0.04`, PF `0.935`, DD `0.3355`, tag `irv4_mechanics_gate_full_ada_doge_sui_20260701_f04_oos_20260701_104508`
