# Structure break cooldown correction — 2026-07-02

Problem caught before wasting the overnight run:

- `scripts/run_structure_break_diagnostic.py` initially swept raw BOS/CHoCH with
  event/side/RR/SL/hold/buffer only.
- Raw BOS/CHoCH is frequent and overtrades; prior smoke already showed all raw
  directions negative.
- Therefore a long raw sweep would mostly re-test a known failure mode.

Fix implemented:

- Added `--cooldown-bars` grid to the runner.
- Added `cooldown_bars` to summary/trades tags.
- Added `per_symbol.csv` output for cross-symbol sanity and concentration checks.

Smoke:

```bash
.venv/bin/python scripts/run_structure_break_diagnostic.py \
  --market crypto \
  --symbols BTCUSDT,ADAUSDT \
  --days 60 \
  --interval-min 60 \
  --events bos \
  --sides long,short \
  --tp-rr 1.5 \
  --sl-atr 1.0 \
  --max-hold 6 \
  --buffer-atr 0.10 \
  --cooldown-bars 0,10 \
  --outdir reports/research/structure_break_cooldown_smoke_20260702
```

Result: cooldown reduced trade count and loss magnitude, but did not create edge
by itself. This is still valuable because the overnight sweep now measures the
correct control variable and reports per-symbol concentration.

Outputs:

- `reports/research/structure_break_cooldown_smoke_20260702/summary.csv`
- `reports/research/structure_break_cooldown_smoke_20260702/per_symbol.csv`
