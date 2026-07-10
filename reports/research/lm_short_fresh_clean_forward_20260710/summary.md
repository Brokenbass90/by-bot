# Level-Memory OOS Pre-Registration Result

- output: `reports/research/lm_short_fresh_clean_forward_20260710`
- base symbols used: `1000PEPEUSDT,ATOMUSDT,AVAXUSDT,DOGEUSDT,HYPEUSDT,ONDOUSDT,TAOUSDT,XRPUSDT`
- best frozen row: `{'respect_min': 0.65, 'lookback': 48, 'rr': 1.2, 'side': 'short', 'elder_mode': 'off', 'trades': 17, 'net_r': -4.2035, 'pf': 0.6171, 'wr': 0.3529, 'dd_r': 5.5839, 'folds_pos': 2, 'stress_net_r': -5.4223, 'stress_pf': 0.5414, 'top_symbol_share': 0.5038, 'top2_share': 0.9732, 'top3_trade_pnl_share': 0.7645, 'folds': '[{"fold": 1, "trades": 2, "net_r": 0.0514, "pf": 1.0462}, {"fold": 2, "trades": 3, "net_r": -3.1987, "pf": 0.0}, {"fold": 3, "trades": 8, "net_r": -1.1268, "pf": 0.75}, {"fold": 4, "trades": 4, "net_r": 0.0707, "pf": 1.0327}]', 'step1_pass': 0, 'step2_pass': 0}`
- OOS selector: `{'windows': 1, 'test_trades': 4, 'test_net_r': 0.1125, 'positive_windows': 1, 'pass': False}`
- holdout: `[{'rr': 1.2, 'trades': 8, 'net_r': -0.4417, 'pf': 0.9032, 'wr': 0.5, 'dd_r': 2.1128, 'folds_pos': 1, 'symbols_present': 'BTCUSDT,DOTUSDT,ETHUSDT', 'symbols_missing_or_no_cache': '', 'positive_symbol_share': 0.3333, 'pass': 0}]`
- verdict: `NO_PROMOTION`

This is strict follow-up for the repaired side-specific exploration pulse. Even PASS only advances to M5 execution parity; no live money or shadow is enabled by this script.
