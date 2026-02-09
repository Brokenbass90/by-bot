# INPLAY runner exit mode (partial TP + trailing)

This repo now supports a **managed exit plan** for INPLAY via
`INPLAY_EXIT_MODE=runner`.

What you get:

* **Partial take-profits** (`tps` + `tp_fracs`)
* **ATR-based trailing stop** (uses highest/lowest since entry)
* **Time stop** (optional)
* Optional: approximate **level-based final TP** from 1h highs/lows

The existing INPLAY entry logic stays the same for now (retest/breakout logic),
but exits are no longer "single fixed RR".

## Environment variables

These are read by `strategies/inplay_wrapper.py`:

| Var | Default | Meaning |
|---|---:|---|
| `INPLAY_EXIT_MODE` | `fixed` | `fixed` = old behavior, `runner` = managed exits |
| `INPLAY_PARTIAL_RS` | `1,2,4` | R-multiples for partial TPs |
| `INPLAY_PARTIAL_FRACS` | `0.5,0.25,0.25` | Fractions of initial qty to close at each TP |
| `INPLAY_TRAIL_ATR_MULT` | `2.5` | ATR multiple for trailing stop |
| `INPLAY_TRAIL_ATR_PERIOD` | `14` | ATR period on 5m candles |
| `INPLAY_TIME_STOP_BARS` | `288` | Close remaining qty after N 5m bars (288=24h). `0` disables |
| `INPLAY_USE_LEVEL_TP` | `1` | If enabled, tries to add/adjust last TP using 1h highs/lows |
| `INPLAY_LEVEL_LOOKBACK_1H` | `72` | Lookback (hours) for the 1h level search |
| `INPLAY_LEVEL_MARGIN_PCT` | `0.004` | Ignore "levels" too close to entry (e.g. 0.4%) |

## Backtest examples

Single symbol:

```bash
INPLAY_EXIT_MODE=runner \
INPLAY_PARTIAL_RS=1,2,4 \
INPLAY_PARTIAL_FRACS=0.5,0.25,0.25 \
INPLAY_TRAIL_ATR_MULT=2.5 \
INPLAY_TIME_STOP_BARS=288 \
python3 backtest/run_month.py --symbols BTCUSDT --strategies inplay --days 30 --tag inplay_runner
```

Combined portfolio (all strategies together):

```bash
INPLAY_EXIT_MODE=runner \
INPLAY_TRAIL_ATR_MULT=2.5 \
python3 backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT \
  --strategies bounce,range,inplay,pump_fade \
  --days 180 \
  --tag portfolio_6m
```
