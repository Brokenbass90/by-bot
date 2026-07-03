# Entry Rework Sweep

Generated: `2026-06-15T18:18:38.908062Z`
Signal TF: `60`, regime TF: `240`, windows: `2`, fee bps: `10.0`

Purpose: raise ASB1/ATT1 trade frequency enough to validate edge, then reject anything that only adds losing trades.

## ASB1

Symbols: `PIXELUSDT, FLOWUSDT`

| Rank | Candidate-like | Symbols with trades | Total trades | Avg expectancy R | Overrides |
|---:|---:|---:|---:|---:|---|
| 1 | 0 | 0 | 0 | 0.0 | `ASB1_COOLDOWN_BARS_5M=36, ASB1_MIN_RANGE_PCT=3.5, ASB1_REGIME_MAX_ATR_PCT=6.5, ASB1_REGIME_MAX_SLOPE_PCT=1.8, ASB1_REGIME_TF=240, ASB1_SIGNAL_TF=60` |

Best combo still has no candidate-like symbols under the anti-overfit screen.

## ATT1

Symbols: `ADAUSDT, ENAUSDT`

| Rank | Candidate-like | Symbols with trades | Total trades | Avg expectancy R | Overrides |
|---:|---:|---:|---:|---:|---|
| 1 | 0 | 1 | 3 | 0.732 | `ATT1_COOLDOWN_BARS_5M=48, ATT1_MIN_R2=0.62, ATT1_SIGNAL_TF=60, ATT1_TOUCH_ATR=0.35` |

Best combo still has no candidate-like symbols under the anti-overfit screen.

