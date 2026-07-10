# Inplay Maker-Fill Gate 2026-07-06

- output: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/reports/research/inplay_maker_long_exact_20260710_20260710_185827`
- scan_csv: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/reports/research/inplay_maker_long_exact_20260710_20260710_185827/scan.csv`
- best: `{'score': 338.0699869227444, 'offset_atr': 0.4, 'validity_bars': 24, 'verdict': {'passed': False, 'reasons': 'stress_weak;concentration_0.511', 'stress_pf': 1.297922, 'stress_net_r': 3.3086, 'stress_trades': 23, 'stress_unfilled_rate': 0.115385, 'folds_positive': 3, 'symbol_concentration': 0.511315, 'gross_profit_by_symbol': {'DOGEUSDT': 7.3702, 'ADAUSDT': 7.044, 'SUIUSDT': 0, '1000PEPEUSDT': 0, 'TAOUSDT': 0}}}`
- verdict: `FAIL`
- reasons: `stress_weak;concentration_0.511`

Pre-registered thresholds: stress PF >= 1.2, 3/4 stress folds positive, unfilled < 50%, symbol concentration < 0.35.
Research-only. PASS can justify shadow/risk=0.0, not automatic live money.
