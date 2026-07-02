# FX native smoke — 2026-07-02

Data:

- `EURUSD`, `GBPUSD`, `USDJPY` from Yahoo Finance M5, ~60d requested.
- `XAUUSD` uses `GC=F` as a free gold-futures research proxy because Yahoo spot
  `XAUUSD=X` is unavailable.

Smoke command:

```bash
.venv/bin/python scripts/run_fx_native_harness.py \
  --pairs XAUUSD,EURUSD \
  --setups round_level_sweep,session_breakout_retest \
  --tp-rr 1.5,2.0 \
  --sl-atr 0.8,1.0 \
  --max-hold 120 \
  --tail-rows 2500 \
  --outdir reports/research/fx_native_harness_smoke_20260702
```

## Result

- `XAUUSD round_level_sweep`: 4 trades on tail-window; best rough row `tp_rr=2.0`,
  `sl_atr=1.0`, netR `+0.942`, PF `1.366`.
- `XAUUSD session_breakout_retest`: 0 trades.
- `EURUSD round_level_sweep`: 0 trades.
- `EURUSD session_breakout_retest`: 0 trades.

## Verdict

Not a candidate yet. Frequency is too low for gate. The useful path is a broader
background sweep on XAU round-level/session logic and less strict breakout/retest
parameters.

Output:

- `reports/research/fx_native_harness_smoke_20260702/summary.csv`
- `reports/research/fx_native_harness_smoke_20260702/trades.csv`
