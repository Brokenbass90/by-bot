# Live forensics candle coverage — 2026-07-03

## Verdict

`missing_candles` is a real diagnostics blocker for live-vs-backtest/forensics.
It is not safe to use current MFE/MAE conclusions for range/pila trades until
candle coverage is fixed.

Fresh local rerun:

```bash
python3 scripts/trade_forensics_report.py \
  --live-events runtime/live_mirror/live_trade_events.jsonl \
  --live-days 45 \
  --cache-dir .cache/klines \
  --interval 5 \
  --post-bars 60 \
  --out-dir reports/trade_forensics \
  --tag live_mirror_45d_20260703
```

Result:

- trades analyzed: `41`
- missing_candles: `31`
- net PnL: `-2.7359`
- PF: `0.571`
- WR: `29.3%`

## Breakdown

| strategy | trades | missing_candles |
|---|---:|---:|
| range | 20 | 20 |
| alt_inplay_breakdown_v1 | 11 | 6 |
| att1_trendline_touch | 7 | 3 |
| flat_resistance_fade | 2 | 2 |

Main reason: many dynamic range symbols are not present in 5m candle cache, both
locally and on the server.

Server cache check:

| symbol | server 5m cache files |
|---|---:|
| APEUSDT | 0 |
| APTUSDT | 0 |
| BERAUSDT | 0 |
| DASHUSDT | 0 |
| DYDXUSDT | 0 |
| GALAUSDT | 0 |
| JUPUSDT | 0 |
| OPUSDT | 0 |
| POLUSDT | 0 |
| PYTHUSDT | 0 |
| RENDERUSDT | 0 |
| ADAUSDT | 56 |
| BTCUSDT | 47 |
| ETHUSDT | 56 |
| DOGEUSDT | 27 |

## Interpretation

This does **not** prove that the live bot entered without candles. It proves that
our forensic/replay cache cannot reconstruct most of those trades. Therefore:

- range/pila remains risk `0.0`;
- do not re-enable range/pila based on scanner cards;
- do not use MFE/MAE conclusions from missing-candle trades;
- require a candle-coverage gate before any range/pila canary.

## Required gate before range/pila live

For every symbol in the live allowlist/dynamic scanner output:

1. 5m cache exists for the full replay window.
2. 1h/4h derived candles can be built or fetched.
3. Forensics can reconstruct entry-to-exit and post-exit windows.
4. Missing candle rate must be `0%` for the canary symbol set.

Only after that: run 180/360d OOS/additivity gate and consider tiny canary.

## Evidence

- `reports/trade_forensics/trade_forensics_20260703_081257_live_mirror_45d_20260703.md`
- `reports/trade_forensics/trade_forensics_20260703_081257_live_mirror_45d_20260703.jsonl`
