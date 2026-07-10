# Inplay Maker-Fill Gate 2026-07-06

- output: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/reports/research/inplay_maker_short_exact_20260710_20260710_185827`
- scan_csv: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/reports/research/inplay_maker_short_exact_20260710_20260710_185827/scan.csv`
- best: `{'score': 1011.5609841900155, 'offset_atr': 0.4, 'validity_bars': 24, 'verdict': {'passed': False, 'reasons': 'concentration_0.364', 'stress_pf': 1.409671, 'stress_net_r': 10.1494, 'stress_trades': 67, 'stress_unfilled_rate': 0.349515, 'folds_positive': 3, 'symbol_concentration': 0.363568, 'gross_profit_by_symbol': {'DOGEUSDT': 12.6972, 'ADAUSDT': 0, 'SUIUSDT': 0, '1000PEPEUSDT': 11.0749, 'TAOUSDT': 11.1518}}}`
- verdict: `FAIL`
- reasons: `concentration_0.364`

Pre-registered thresholds: stress PF >= 1.2, 3/4 stress folds positive, unfilled < 50%, symbol concentration < 0.35.
Research-only. PASS can justify shadow/risk=0.0, not automatic live money.
