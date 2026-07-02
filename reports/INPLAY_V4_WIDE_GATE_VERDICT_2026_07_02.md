# InPlay V4 wide gate verdict — 2026-07-02

Source:

- `reports/research/irv4_wide_gate_20260702_20260702_044439/summary.md`
- `reports/research/irv4_wide_gate_20260702_20260702_044439/runs.csv`

## Raw script result

The original gate script printed `PASS`:

- symbols: `ADAUSDT,DOGEUSDT,SUIUSDT,DOTUSDT,LTCUSDT,LINKUSDT,SOLUSDT`
- OOS folds: 4
- OOS total trades: 36
- OOS total net: +0.82R
- oos_selector reason: `robust_plateau`

OOS rows:

| fold | trades | netR | PF | DD |
|---:|---:|---:|---:|---:|
| 1 | 16 | +0.06 | 1.029 | 1.4725 |
| 2 | 15 | +0.81 | 1.490 | 0.6000 |
| 3 | 3 | +0.28 | 2.081 | 0.2758 |
| 4 | 2 | -0.33 | 0.018 | 0.3364 |

## Corrected strict verdict

This is **not canary-grade**.

Under the stricter pre-registered gate:

- `min_trades_total >= 40`
- `min_trades_per_fold >= 8`
- `max_peak_ratio <= 3.0`
- `robustness > 0`

the same OOS folds evaluate as:

```text
passes=False
reason=insufficient_trades_36
robustness=-0.0679
total_trades=36
min_fold_trades=2
```

## Decision

- Do not promote InPlay V4 to canary.
- At most: shadow/paper observation.
- Next research step: expand universe / increase frequency, then rerun with strict gate.

## Code fix applied

`scripts/inplay_v4_mechanics_gate.py` was hardened so future gates no longer pass
thin OOS folds:

- default `--min-oos-trades` changed from 18 to 40;
- added `--min-oos-trades-per-fold`, default 8;
- `max_peak_ratio` restored to 3.0;
- `min_robustness=0.0` enforced via `bot.oos_selector`.

