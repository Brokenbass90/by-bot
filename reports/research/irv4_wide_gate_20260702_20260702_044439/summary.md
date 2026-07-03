# InPlay V4 mechanics gate — PASS

- symbols: `ADAUSDT,DOGEUSDT,SUIUSDT,DOTUSDT,LTCUSDT,LINKUSDT,SOLUSDT`
- folds: `4` rolling train/test
- train_days: `120`
- test_days: `60`
- grid_combos_per_fold: `36`
- OOS total trades: `36`
- OOS total net: `0.82R`
- oos_selector: `passes=True`, reason `robust_plateau`, robustness `-0.068`
- raw runs: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/reports/research/irv4_wide_gate_20260702_20260702_044439/runs.csv`

## Selected params by fold

- fold 1: score `14.181750` — IRV4_TP_RR=2.0, IRV4_RETEST_MIN_QUALITY=0.35, IRV4_LEVEL_ENTRY_VALIDITY_BARS=2, IRV4_LEVEL_ENTRY_MAX_CHASE_ATR=0.4
- fold 2: score `3.807500` — IRV4_TP_RR=2.5, IRV4_RETEST_MIN_QUALITY=0.35, IRV4_LEVEL_ENTRY_VALIDITY_BARS=2, IRV4_LEVEL_ENTRY_MAX_CHASE_ATR=0.4
- fold 3: score `6.190250` — IRV4_TP_RR=3.0, IRV4_RETEST_MIN_QUALITY=0.35, IRV4_LEVEL_ENTRY_VALIDITY_BARS=4, IRV4_LEVEL_ENTRY_MAX_CHASE_ATR=0.4
- fold 4: score `9.734625` — IRV4_TP_RR=3.0, IRV4_RETEST_MIN_QUALITY=0.55, IRV4_LEVEL_ENTRY_VALIDITY_BARS=2, IRV4_LEVEL_ENTRY_MAX_CHASE_ATR=0.4

## OOS rows

- fold 1: trades `16`, net `0.06`, PF `1.029`, DD `1.4725`, tag `irv4_wide_gate_20260702_f01_oos_20260702_044439`
- fold 2: trades `15`, net `0.81`, PF `1.490`, DD `0.6000`, tag `irv4_wide_gate_20260702_f02_oos_20260702_044439`
- fold 3: trades `3`, net `0.28`, PF `2.081`, DD `0.2758`, tag `irv4_wide_gate_20260702_f03_oos_20260702_044439`
- fold 4: trades `2`, net `-0.33`, PF `0.018`, DD `0.3364`, tag `irv4_wide_gate_20260702_f04_oos_20260702_044439`
