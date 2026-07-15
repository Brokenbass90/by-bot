# Pattern Atlas v1 — bounded multi-coin discovery contract

**Status:** preregistered discovery completed on 2026-07-15; the sealed 120-day holdout remains unscored, no strategy was promoted, and no live state was touched.

The atlas tests six fixed causal H1 hypotheses across the exact hash-pinned 13-coin M5 cohort: horizontal breakout, failed-break reversal, and horizontal rejection, with long and short represented as separate physical hypotheses. Signals use only a completed H1 bar and its prior 20 H1 bars. Outcomes begin at the next H1 open and are measured at 6h, 24h, 72h, and 7d with return, MFE, MAE, sample size, per-symbol means, largest-symbol share, and HHI.

The last 120 days are sealed. The loader verifies every immutable source hash, decodes only the exact discovery prefix, and stops before decoding the first holdout row. Same-pattern observations are separated by 168 H1 bars so the longest reported path does not overlap within a symbol/pattern. Empty and concentrated cells remain visible.

This is a pattern atlas, not a backtest. It omits fees, slippage, funding, fill probability, exits, portfolio overlap, and sizing. It produces no p-values and is never promotion-eligible. Any interesting cell still requires a separately frozen sealed-holdout test, external symbols, a costed execution model, and the normal promotion gate.

Sloped/diagonal levels are intentionally excluded: the project does not yet have a promotion-grade causal sloped-level snapshot contract. Adding them now would create a prettier but unauditable result.

Integrity-only validation:

```bash
python3 scripts/run_multicoin_pattern_atlas_v1.py --integrity-only
```

Reproduce the frozen discovery run:

```bash
python3 scripts/run_multicoin_pattern_atlas_v1.py \
  --output reports/research/multicoin_pattern_atlas_v1_20260715/receipt.json
```

Canonical inputs:

- `configs/preregistered/multicoin_pattern_atlas_v1_20260715.json`
- `configs/preregistered/event_long_dev13_uniform_m5_window_v1_20260714.json`
- `bot/closed_bar_aggregation_v1.py`
- `scripts/run_multicoin_pattern_atlas_v1.py`

## Completed discovery receipt

The hash-verified discovery run produced `20,372` observation paths and `8,840`
time-sampled control paths across `24` fixed pattern/horizon cells.  The receipt
reports `sealed_holdout_scored=false`, `promotion_eligible=false`, and no broker
or live calls.

Only one cell is retained as a bounded successor hypothesis:
`horizontal_breakout_long` at 72 hours (`N=909`, mean `+54.499 bps`, excess to
the frozen time/side control `+91.002 bps`, 10/13 per-symbol means positive,
largest-symbol share `7.9%`).  Its median is `-49.236 bps`, hit rate `47.96%`,
and p25 `-442.558 bps`, so the mean is fat-tail dependent.  It is not a
trade-ready signal.  The next permitted step is one separately frozen, costed
exit/retest contract on the still-sealed holdout; the other 23 cells must not
be rescued post hoc.

Canonical receipt:
`reports/research/multicoin_pattern_atlas_v1_20260715/receipt.json`.
