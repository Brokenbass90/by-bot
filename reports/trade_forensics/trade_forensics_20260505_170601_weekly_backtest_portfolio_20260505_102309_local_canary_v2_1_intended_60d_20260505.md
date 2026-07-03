# Trade Forensics - weekly_backtest_portfolio_20260505_102309_local_canary_v2_1_intended_60d_20260505

Generated UTC: 2026-05-05 17:06:01

Trades analyzed: **10**

Net PnL: **3.6677** | PF: **5.617** | WR: **80.0%**

## Strategy Summary

| Strategy | Trades | Net | PF | WR | Avg MFE % | Avg MAE % | Main Verdicts |
|---|---:|---:|---:|---:|---:|---:|---|
| alt_support_bounce_v1 | 1 | -0.5050 | 0.000 | 0.0% | 2.21 | -1.55 | stop_then_reversed:1 |
| alt_trendline_touch_v1 | 9 | 4.1727 | 15.418 | 88.9% | 2.34 | -0.84 | gave_back_profit:6, stop_then_reversed:2, entry_failed_fast:1 |

## Worst Trades

| Exit UTC | Strategy | Symbol | Side | PnL | MFE % | MAE % | Post 6 bars % | Verdict | Reason |
|---|---|---|---|---:|---:|---:|---:|---|---|
| 2026-03-29 22:40:00 | alt_support_bounce_v1 | LTCUSDT | long | -0.5050 | 2.21 | -1.55 | 0.70 | stop_then_reversed | asb1_support_bounce+SL |
| 2026-03-31 23:55:00 | alt_trendline_touch_v1 | LTCUSDT | short | -0.2894 | 0.34 | -1.48 | 0.02 | entry_failed_fast | att1_short_trendline tl=53.9502 slope=-0.437%/d rsi=50.3+EOP |
| 2026-03-27 08:45:00 | alt_trendline_touch_v1 | SOLUSDT | short | 0.3455 | 1.82 | -0.47 | 0.27 | gave_back_profit | att1_short_trendline tl=86.3866 slope=-2.668%/d rsi=41.4+TRAIL_SL |
| 2026-03-27 09:20:00 | alt_trendline_touch_v1 | SUIUSDT | short | 0.3914 | 1.88 | -0.32 | 0.14 | gave_back_profit | att1_short_trendline tl=0.9315 slope=-0.628%/d rsi=67.4+TRAIL_SL |
| 2026-03-27 10:45:00 | alt_trendline_touch_v1 | ADAUSDT | short | 0.4341 | 2.12 | -0.18 | 0.85 | stop_then_reversed | att1_short_trendline tl=0.2546 slope=-2.430%/d rsi=42.1+TRAIL_SL |
| 2026-03-27 10:45:00 | alt_trendline_touch_v1 | LINKUSDT | short | 0.5218 | 2.37 | -0.65 | 0.88 | stop_then_reversed | att1_short_trendline tl=8.9467 slope=-1.050%/d rsi=46.7+TRAIL_SL |
| 2026-03-29 22:50:00 | alt_trendline_touch_v1 | LINKUSDT | short | 0.5412 | 2.70 | -0.70 | -0.49 | gave_back_profit | att1_short_trendline tl=8.4990 slope=-2.184%/d rsi=49.3+TP1+TRAIL_SL |
| 2026-03-29 22:55:00 | alt_trendline_touch_v1 | DOTUSDT | short | 0.5831 | 2.97 | -0.94 | -1.65 | gave_back_profit | att1_short_trendline tl=1.2680 slope=-2.428%/d rsi=40.2+TP1+TRAIL_SL |
| 2026-03-27 11:05:00 | alt_trendline_touch_v1 | ETHUSDT | short | 0.6842 | 3.22 | -0.61 | 0.41 | gave_back_profit | att1_short_trendline tl=2067.2259 slope=-1.510%/d rsi=50.4+TP1+TRAIL_SL |
| 2026-03-26 09:40:00 | alt_trendline_touch_v1 | ETHUSDT | short | 0.9607 | 3.62 | -2.18 | 0.22 | gave_back_profit | att1_short_trendline tl=2173.2849 slope=-2.553%/d rsi=69.0+TP1+TRAIL_SL |

## AI Follow-Up Prompts

- If many losses are `stop_then_reversed`, test wider SL or delayed confirmation.
- If many losses are `entry_failed_fast`, test stricter entry filters or regime/symbol gating.
- If wins are often `tp_then_continued`, test wider TP/trailing logic.
- If `missing_candles` appears often, refresh the cache before trusting this report.
