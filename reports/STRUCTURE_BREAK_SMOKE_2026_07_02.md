# Structure break smoke — 2026-07-02

Scope: quick crypto smoke, 4 symbols (`BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT`), 180d,
1h bars, raw BOS/CHoCH, fixed-R exit. This checks whether the frequent event has
obvious raw edge before a heavier gate.

Command:

```bash
.venv/bin/python scripts/run_structure_break_diagnostic.py \
  --market crypto \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
  --days 180 \
  --interval-min 60 \
  --events bos,choch \
  --sides long,short \
  --tp-rr 1.5 \
  --sl-atr 1.0 \
  --max-hold 12 \
  --buffer-atr 0.10 \
  --outdir reports/research/structure_break_crypto_smoke_20260702
```

## Result

| Event | Side | Trades | Net R | PF |
|---|---|---:|---:|---:|
| BOS | long | 691 | -234.64 | 0.558 |
| BOS | short | 717 | -134.61 | 0.725 |
| CHoCH | long | 241 | -57.07 | 0.662 |
| CHoCH | short | 261 | -99.62 | 0.514 |

## Verdict

Raw BOS/CHoCH is not a live candidate. It is frequent, but unfiltered it overtrades
and loses. The overnight diagnostic should test whether event/side/hold/ATR buffers
create any robust pocket; if not, the next step is adding regime/retest filters before
spending more compute.

Output:

- `reports/research/structure_break_crypto_smoke_20260702/summary.csv`
- `reports/research/structure_break_crypto_smoke_20260702/trades.csv`
