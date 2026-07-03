# SpikeFadeV3 robustness gate — FAIL

- symbol: `LINKUSDT`
- folds: `4` rolling train/test
- train_days: `240`
- test_days: `90`
- grid_combos_per_fold: `32`
- OOS total trades: `29`
- OOS total net: `0.93R`
- reasons: `oos_net_too_low:0.93, oos_pf_too_low:1.144, bad_oos_fold:-1.10, fee_stress_failed:4`
- raw runs: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/reports/research/sfv3_robust_gate_20260701_v2_20260701_073903/runs.csv`

## Selected params by fold

- fold 1: score `4.677` — SFV3_LEVEL_TOL_ATR=0.35, SFV3_REJECT_FRAC=0.55, SFV3_SPIKE_MIN_PCT=4.0, SFV3_STOP_BUFFER_ATR=0.40, SFV3_TAG_LEVEL_ATR=0.8
- fold 2: score `5.622` — SFV3_LEVEL_TOL_ATR=0.35, SFV3_REJECT_FRAC=0.55, SFV3_SPIKE_MIN_PCT=4.0, SFV3_STOP_BUFFER_ATR=0.25, SFV3_TAG_LEVEL_ATR=0.8
- fold 3: score `9.251` — SFV3_LEVEL_TOL_ATR=0.35, SFV3_REJECT_FRAC=0.55, SFV3_SPIKE_MIN_PCT=4.0, SFV3_STOP_BUFFER_ATR=0.25, SFV3_TAG_LEVEL_ATR=0.8
- fold 4: score `14.290` — SFV3_LEVEL_TOL_ATR=0.35, SFV3_REJECT_FRAC=0.50, SFV3_SPIKE_MIN_PCT=4.0, SFV3_STOP_BUFFER_ATR=0.40, SFV3_TAG_LEVEL_ATR=0.8

## OOS rows

- fold 1: trades `11`, net `0.01`, PF `1.003`, DD `1.2731`, tag `sfv3_robust_gate_20260701_v2_f01_oos_20260701_073903`
- fold 2: trades `8`, net `1.16`, PF `1.679`, DD `0.5453`, tag `sfv3_robust_gate_20260701_v2_f02_oos_20260701_073903`
- fold 3: trades `8`, net `-1.10`, PF `0.535`, DD `1.3768`, tag `sfv3_robust_gate_20260701_v2_f03_oos_20260701_073903`
- fold 4: trades `2`, net `0.86`, PF `inf`, DD `0.0180`, tag `sfv3_robust_gate_20260701_v2_f04_oos_20260701_073903`

## Fee stress rows

- fold 1 stress `10:5`: trades `11`, net `-0.39`, PF `0.849`, DD `1.5471`
- fold 1 stress `12:8`: trades `11`, net `-1.07`, PF `0.613`, DD `1.7392`
- fold 2 stress `10:5`: trades `8`, net `0.90`, PF `1.491`, DD `0.5825`
- fold 2 stress `12:8`: trades `8`, net `0.72`, PF `1.372`, DD `0.6072`
- fold 3 stress `10:5`: trades `8`, net `-1.41`, PF `0.448`, DD `1.6024`
- fold 3 stress `12:8`: trades `8`, net `-1.63`, PF `0.394`, DD `1.7626`
- fold 4 stress `10:5`: trades `2`, net `0.80`, PF `inf`, DD `0.0300`
- fold 4 stress `12:8`: trades `2`, net `0.76`, PF `inf`, DD `0.0360`

## Cross-symbol sanity rows

- fold 1 `SOLUSDT`: trades `4`, net `-0.12`, PF `0.858`, DD `0.8265`
- fold 1 `SUIUSDT`: trades `6`, net `-0.89`, PF `0.341`, DD `1.1030`
- fold 1 `DOGEUSDT`: trades `10`, net `-0.15`, PF `0.937`, DD `1.5460`
- fold 1 `ADAUSDT`: trades `4`, net `-0.19`, PF `0.824`, DD `1.0828`
- fold 2 `SOLUSDT`: trades `9`, net `-1.44`, PF `0.487`, DD `2.0416`
- fold 2 `SUIUSDT`: trades `20`, net `-0.01`, PF `0.997`, DD `1.8436`
- fold 2 `DOGEUSDT`: trades `9`, net `2.01`, PF `2.628`, DD `0.9338`
- fold 2 `ADAUSDT`: trades `6`, net `-0.54`, PF `0.694`, DD `1.4464`
- fold 3 `SOLUSDT`: trades `6`, net `-0.48`, PF `0.708`, DD `0.5901`
- fold 3 `SUIUSDT`: trades `14`, net `1.85`, PF `1.755`, DD `1.1566`
- fold 3 `DOGEUSDT`: trades `13`, net `-1.24`, PF `0.695`, DD `2.3685`
- fold 3 `ADAUSDT`: trades `11`, net `0.93`, PF `1.413`, DD `1.1282`
- fold 4 `SOLUSDT`: trades `1`, net `0.70`, PF `inf`, DD `0.0118`
- fold 4 `SUIUSDT`: trades `7`, net `1.47`, PF `2.845`, DD `0.4678`
- fold 4 `DOGEUSDT`: trades `1`, net `0.57`, PF `inf`, DD `0.0180`
- fold 4 `ADAUSDT`: trades `2`, net `0.51`, PF `inf`, DD `0.0211`
