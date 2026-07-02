# ARF2 failed-breakout diagnostic — 2026-07-02

Scope: cheap local diagnostic on cached crypto data, 17 mid-cap symbols, 360d, 6/2-ish
cost model inside diagnostic. This is not a canary gate; it decides whether the
failed-breakout rewrite deserves heavier OOS.

## Result

| Variant | Trades | Net R | PF | WR | Fold net R |
|---|---:|---:|---:|---:|---|
| failed_breakout | 177 | +6.02 | 1.053 | 42.4% | +9.87, +11.10, -11.23, -3.71 |
| failed_breakout_volfade | 149 | +4.24 | 1.045 | 43.6% | +10.33, -2.05, +3.26, -7.30 |
| failed_breakout_level | 136 | -65.58 | 0.532 | 25.7% | all red |
| failed_breakout_range | 0 | 0.00 | 0.000 | 0.0% | no frequency |

## Verdict

NO-GO for live / canary. The plain failed-breakout logic is better than old
“fade just because price touched resistance”, but the edge is too thin and not
fold-stable. Two of four chronological folds are red.

Useful next research, if revisited:

- symbol-gated subtests: DOGE, XRP, ONDO were the strongest contributors;
- do not use `level_entry` with the current failed-breakout geometry — it lost
  heavily in this diagnostic;
- `range_filter` as currently configured is too strict for this event type.

Output:

- `reports/research/arf2_failed_breakout_diag_20260702/summary.csv`
- `reports/research/arf2_failed_breakout_diag_20260702/signals.csv`
