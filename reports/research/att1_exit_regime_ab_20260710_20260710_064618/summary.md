# ATT1 Exit/Regime A/B 2026-07-10

Research-only. No live config/order/risk change.

- symbols: `BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,LTCUSDT,DOTUSDT,SUIUSDT`
- folds: `4` x `90` days, end `2026-04-01`
- costs: fee `6.0` bps, slippage `2.0` bps, next-open `True`

| variant | regime | folds+ | trades | net pnl | PF | winrate | top exits |
|---|---|---:|---:|---:|---:|---:|---|
| small_tp1 | all_regimes | 4/4 | 379 | 19.21 | 1.283 | 0.579 | att1_short_trendline tl=3.5183 slope=-1.844%/d rsi=61.8+SL:1, att1_short_trendline tl=13.0804 slope=-1.675%/d rsi=53.8+TP1+TRAIL_SL:1, att1_short_trendline tl=2.3063 slope=-3.126%/d rsi=52.0+TRAIL_SL:1, att1_short_trendline tl=0.6550 slope=-2.535%/d rsi=50.7+TRAIL_SL:1 |
| base | all_regimes | 4/4 | 379 | 18.78 | 1.277 | 0.579 | att1_short_trendline tl=3.5183 slope=-1.844%/d rsi=61.8+SL:1, att1_short_trendline tl=13.0804 slope=-1.675%/d rsi=53.8+TP1+TRAIL_SL:1, att1_short_trendline tl=2.3063 slope=-3.126%/d rsi=52.0+TRAIL_SL:1, att1_short_trendline tl=0.6550 slope=-2.535%/d rsi=50.7+TRAIL_SL:1 |
| small_tp1 | trend_only | 2/4 | 293 | 13.06 | 1.258 | 0.571 | att1_short_trendline tl=13.0804 slope=-1.675%/d rsi=53.8+TP1+TRAIL_SL:1, att1_short_trendline tl=2.3063 slope=-3.126%/d rsi=52.0+TRAIL_SL:1, att1_short_trendline tl=0.6550 slope=-2.535%/d rsi=50.7+TRAIL_SL:1, att1_short_trendline tl=12.4831 slope=-0.443%/d rsi=64.4+TP1+TRAIL_SL:1 |
| base | trend_only | 2/4 | 293 | 12.81 | 1.257 | 0.571 | att1_short_trendline tl=13.0804 slope=-1.675%/d rsi=53.8+TP1+TRAIL_SL:1, att1_short_trendline tl=2.3063 slope=-3.126%/d rsi=52.0+TRAIL_SL:1, att1_short_trendline tl=0.6550 slope=-2.535%/d rsi=50.7+TRAIL_SL:1, att1_short_trendline tl=12.4831 slope=-0.443%/d rsi=64.4+TP1+TRAIL_SL:1 |
| early_be_05 | trend_only | 3/4 | 315 | 8.73 | 1.255 | 0.719 | att1_short_trendline tl=13.0804 slope=-1.675%/d rsi=53.8+TP1+TRAIL_SL:1, att1_short_trendline tl=2.3063 slope=-3.126%/d rsi=52.0+TRAIL_SL:1, att1_short_trendline tl=0.6550 slope=-2.535%/d rsi=50.7+TRAIL_SL:1, att1_short_trendline tl=12.4831 slope=-0.443%/d rsi=64.4+TP1+TRAIL_SL:1 |
| early_be_05 | all_regimes | 3/4 | 418 | 11.69 | 1.249 | 0.722 | att1_short_trendline tl=3.5183 slope=-1.844%/d rsi=61.8+SL:1, att1_short_trendline tl=13.0804 slope=-1.675%/d rsi=53.8+TP1+TRAIL_SL:1, att1_short_trendline tl=2.3063 slope=-3.126%/d rsi=52.0+TRAIL_SL:1, att1_short_trendline tl=0.6550 slope=-2.535%/d rsi=50.7+TRAIL_SL:1 |
| pure_trail | all_regimes | 2/4 | 68 | 1.43 | 1.165 | 0.540 | att1_short_trendline tl=76.3050 slope=-1.205%/d rsi=54.2+TRAIL_SL:1, att1_short_trendline tl=1613.2321 slope=-2.071%/d rsi=51.8+TRAIL_SL:1, att1_short_trendline tl=94787.3297 slope=-1.344%/d rsi=50.4+SL:1, att1_short_trendline tl=1825.9483 slope=-2.276%/d rsi=45.4+SL:1 |
| pure_trail | trend_only | 2/4 | 66 | 0.61 | 1.067 | 0.513 | att1_short_trendline tl=76.3050 slope=-1.205%/d rsi=54.2+TRAIL_SL:1, att1_short_trendline tl=1613.2321 slope=-2.071%/d rsi=51.8+TRAIL_SL:1, att1_short_trendline tl=94787.3297 slope=-1.344%/d rsi=50.4+SL:1, att1_short_trendline tl=1825.9483 slope=-2.276%/d rsi=45.4+SL:1 |
| early_be_03 | trend_only | 3/4 | 322 | 1.38 | 1.053 | 0.692 | att1_short_trendline tl=13.0804 slope=-1.675%/d rsi=53.8+TP1+TRAIL_SL:1, att1_short_trendline tl=2.3063 slope=-3.126%/d rsi=52.0+TRAIL_SL:1, att1_short_trendline tl=0.6550 slope=-2.535%/d rsi=50.7+TRAIL_SL:1, att1_short_trendline tl=0.6401 slope=-2.549%/d rsi=58.2+SL:1 |
| early_be_03 | all_regimes | 2/4 | 434 | 1.22 | 1.034 | 0.696 | att1_short_trendline tl=3.5183 slope=-1.844%/d rsi=61.8+TRAIL_SL:1, att1_short_trendline tl=13.0804 slope=-1.675%/d rsi=53.8+TP1+TRAIL_SL:1, att1_short_trendline tl=2.3063 slope=-3.126%/d rsi=52.0+TRAIL_SL:1, att1_short_trendline tl=0.6550 slope=-2.535%/d rsi=50.7+TRAIL_SL:1 |

Promotion rule for later review: no live change unless a variant beats base on PF/net, has enough trades, and holds across folds.
This runner intentionally does not decide promotion by itself.
