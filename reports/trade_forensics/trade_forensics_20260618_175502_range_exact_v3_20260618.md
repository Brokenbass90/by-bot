# Trade Forensics - range_exact_v3_20260618

Generated UTC: 2026-06-18 17:55:02

Trades analyzed: **14**

Net PnL: **-0.2542** | PF: **0.885** | WR: **35.7%**

## Strategy Summary

| Strategy | Trades | Net | PF | WR | Avg MFE % | Avg MAE % | Main Verdicts |
|---|---:|---:|---:|---:|---:|---:|---|
| range | 14 | -0.2542 | 0.885 | 35.7% | 0.98 | -0.65 | stop_then_reversed:6, tp_then_continued:3, stopped_no_reversal_yet:2 |

## Worst Trades

| Exit UTC | Strategy | Symbol | Side | PnL | MFE % | MAE % | Post 6 bars % | Verdict | Reason |
|---|---|---|---|---:|---:|---:|---:|---|---|
| 2026-06-17 19:40:24 | range | POLUSDT | long | -0.3870 | 0.04 | -0.68 | 0.94 | stop_then_reversed | range-long: sup=0.076223 mid=0.077491 w=0.002537 atr5=0.000461 rr=6.94 min_rr=3.00 |
| 2026-06-17 19:29:30 | range | DASHUSDT | long | -0.2844 | 2.05 | -1.30 | 0.14 | gave_back_profit | range-long: sup=36.881429 mid=38.037143 w=2.311429 atr5=0.199286 rr=6.31 min_rr=3.00 |
| 2026-06-17 19:54:14 | range | GALAUSDT | long | -0.2805 | -0.07 | -0.71 | 1.24 | stop_then_reversed | range-long: sup=0.002669 mid=0.002717 w=0.000097 atr5=0.000021 rr=6.02 min_rr=3.00 |
| 2026-06-17 19:42:50 | range | GALAUSDT | long | -0.2769 | 0.07 | -1.23 | 1.28 | stop_then_reversed | range-long: sup=0.002669 mid=0.002717 w=0.000097 atr5=0.000021 rr=3.03 min_rr=3.00 |
| 2026-06-17 14:47:36 | range | DOGEUSDT | long | -0.2340 | 0.01 | -0.82 | 1.18 | stop_then_reversed | range-long: sup=0.086199 mid=0.087726 w=0.003056 atr5=0.000224 rr=5.17 min_rr=3.00 |
| 2026-06-18 04:03:47 | range | APTUSDT | long | -0.2095 | -0.02 | -0.70 | -0.05 | stopped_no_reversal_yet | range-long: sup=0.659129 mid=0.677014 w=0.035771 atr5=0.002307 rr=5.82 min_rr=3.00 |
| 2026-06-17 08:38:45 | range | DOGEUSDT | long | -0.1915 | 0.00 | -0.84 | 0.07 | stopped_no_reversal_yet | range-long: sup=0.086369 mid=0.087811 w=0.002886 atr5=0.000182 rr=3.33 min_rr=3.00 |
| 2026-06-17 22:03:40 | range | OPUSDT | long | -0.1832 | 0.90 | -1.05 | 2.68 | stop_then_reversed | range-long: sup=0.106301 mid=0.108811 w=0.005020 atr5=0.000996 rr=3.62 min_rr=3.00 |
| 2026-06-17 23:20:52 | range | APEUSDT | short | -0.1576 | 0.23 | -0.71 | 1.87 | stop_then_reversed | range-short: res=0.133744 mid=0.130266 w=0.006956 atr5=0.000828 rr=3.80 min_rr=3.00 |
| 2026-06-17 11:40:58 | range | BERAUSDT | long | 0.0642 | 1.11 | -0.28 | 1.19 | tp_then_continued | range-long: sup=0.251129 mid=0.259736 w=0.017214 atr5=0.001079 rr=5.10 min_rr=3.00 |
| 2026-06-18 02:22:47 | range | APEUSDT | short | 0.0992 | 1.46 | -0.42 | 0.56 | clean_win | range-short: res=0.133744 mid=0.130266 w=0.006956 atr5=0.000722 rr=4.64 min_rr=3.00 |
| 2026-06-17 14:15:30 | range | PYTHUSDT | long | 0.5679 | 2.68 | -0.03 | 1.14 | tp_then_continued | range-long: sup=0.038413 mid=0.039473 w=0.002120 atr5=0.000184 rr=4.80 min_rr=3.00 |
| 2026-06-17 18:00:53 | range | DYDXUSDT | short | 0.5885 | 3.42 | -0.07 | 1.40 | tp_then_continued | range-short: res=0.126680 mid=0.122830 w=0.007700 atr5=0.000776 rr=4.78 min_rr=3.00 |
| 2026-06-17 16:28:19 | range | DOGEUSDT | long | 0.6306 | 1.83 | -0.23 | -0.19 | clean_win | range-long: sup=0.086199 mid=0.087726 w=0.003056 atr5=0.000261 rr=4.97 min_rr=3.00 |

## AI Follow-Up Prompts

- If many losses are `stop_then_reversed`, test wider SL or delayed confirmation.
- If many losses are `entry_failed_fast`, test stricter entry filters or regime/symbol gating.
- If wins are often `tp_then_continued`, test wider TP/trailing logic.
- If `missing_candles` appears often, refresh the cache before trusting this report.
