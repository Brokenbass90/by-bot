# SpikeFadeV3 robustness gate — FAIL

- symbol: `LINKUSDT`
- folds: `1` rolling train/test
- train_days: `60`
- test_days: `30`
- grid_combos_per_fold: `1`
- OOS total trades: `0`
- OOS total net: `0.00R`
- reasons: `need_at_least_3_oos_folds, too_few_oos_trades:0, oos_net_too_low:0.00, oos_pf_too_low:0.000, fee_stress_failed:1`
- raw runs: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/reports/research/sfv3_gate_smoke_20260701_054741/runs.csv`

## Selected params by fold

- fold 1: score `-1000000000.000` — SFV3_LEVEL_TOL_ATR=0.35, SFV3_REJECT_FRAC=0.50, SFV3_SPIKE_MIN_PCT=4.0, SFV3_STOP_BUFFER_ATR=0.25, SFV3_TAG_LEVEL_ATR=0.6

## OOS rows

- fold 1: trades `0`, net `0.00`, PF `0.000`, DD `0.0000`, tag `sfv3_gate_smoke_f01_oos_20260701_054741`

## Fee stress rows

- fold 1 stress `10:5`: trades `0`, net `0.00`, PF `0.000`, DD `0.0000`
