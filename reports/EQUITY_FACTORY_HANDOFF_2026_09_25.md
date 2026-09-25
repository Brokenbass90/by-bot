# Deep equity data handoff — P_AKC_OSTATOCHNYY_MOMENT

Status: **deep archive acquired; full fixed-universe acceptance BLOCKED_DATA**.
No hypothesis/confirmation executed. No Factory queue, frozen strategy, production
cache or accepted original archive modified.

Local dataset:
`research_lab/data/alpaca_pit_daily_deep_20260925/`
Raw GET receipts (private): `.private/equity_depth_20260925/raw/`.
Tracked manifest: `reports/EQUITY_DEEP_HISTORY_MANIFEST_2026_09_25.json`.
Quality receipt: `reports/EQUITY_DEEP_HISTORY_QUALITY_2026_09_25.json`.

- Requested 2016-01-01 through completed date 2026-09-23, all **962** symbols in
  original accepted membership. 961 validated files, **2,032,108** daily rows.
- 618 symbols reach 2016; 671 reach 2018 or earlier. No pre-listing bars invented.
- Original membership/universe/reference metadata byte-identical. Original 38
  quarantined symbols not reinstated. Observed spans in copied membership still
  describe original snapshot; deep spans are in the quality receipt.
- Legacy JSON encoding unchanged: schema ID `massive_adjusted_daily_symbol_v1`,
  `records` fields `t,o,h,l,c,v,vw,n`, epoch milliseconds, payload hash.
  **Actual new source is Alpaca SIP**, split-adjusted, `asof=-`; legacy schema ID
  describes encoding only. Massive 2016 request returned HTTP403 plan restriction.
- 35,639 zero-trade provider observations preserved exactly, with zero volume,
  trade count and VWAP. No fill-forward or fabricated dollar volume.
- Every accepted file hash, payload hash, sorted unique timestamps, interval and
  exact field set checked. 442,535 overlapping closes compared; 11,022 differ
  by more than 1ppm. This is **not proven provider parity**, not a replacement of
  existing strategy results. No assertion of causal vintage price-filter parity.

Concrete remaining data conflicts (existing integrity rules, not new strategy gates):

1. **SPCX**: 2024-11-20 provider bar has volume 184, 11 trades and VWAP 0.
   Raw response preserved; symbol normalization rejected. Do not silently drop it
   from the fixed universe or invent VWAP from close. Obtain corrected independent
   source evidence for this bar with explicit provenance before accepting it.
2. **XTKG**: 23 provider bars after frozen delisting boundary. Same
   `ticker_identity_conflict_bar_after_delist` condition as original validator.
   Raw/normalized history retained but not accepted for blind run. Resolve identity
   against original reference; do not trim/relabel merely to make validation pass.

Current-liquidity candidate selection bias already existed and remains unresolved.
Deeper history does not create full-market PIT or remove survivorship/rename risk.
`asof=-` avoids automatic rename stitching; it is not proof against ticker reuse.

Consumer is existing `research_lab/fabrika/portfeli.py::zagruzit_akcii` in Claude's
checkout. It currently names the old archive. No code/path change was made there.
Give Factory the separate dataset + manifest + quarantine receipt; do not silently
swap `alpaca_pit_daily_v1`, drop conflicted symbols, change prereg or run confirmation.

Offline reproducibility:

```bash
.venv/bin/python -m pytest -q tests/test_extend_equity_history_readonly.py
PYTHONPATH=. .venv/bin/python scripts/validate_equity_history_extension.py \
  --source research_lab/data/alpaca_pit_daily_v1 \
  --archive research_lab/data/alpaca_pit_daily_deep_20260925 \
  --report reports/EQUITY_DEEP_HISTORY_QUALITY_2026_09_25.json
```

Downloader supports saved-page resume with bounded GET retries and a 50GB free-space
guard. Original acquisition used bounded `caffeinate`; it finished, no heavy job
needs to keep Mac awake. Dataset remains local; Git stores source/tests/manifests,
not millions of raw bars. Provider docs:
[Alpaca historical bars](https://docs.alpaca.markets/us/reference/stockbarsingle-1),
[Massive adjusted aggregates](https://www.massive.com/docs/rest/stocks/aggregates/custom-bars).
