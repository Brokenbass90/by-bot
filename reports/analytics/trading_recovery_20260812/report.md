# Recovery session — 12 August 2026

**Verdict:** Infrastructure and measurement advanced materially; no new money sleeve is honestly promotable yet.

## $1,000 per sleeve: mechanical evidence, not a forecast

| Sleeve | Stage | Mechanical year-end | Evidence range | Red months | Status |
|---|---|---:|---:|---|---|
| ATT1 Bybit canary | CANARY | $1,008.86 | — | 2/12 in older narrow replay; live clean N still insufficient | MECHANICAL_ONLY |
| XSEC neutral crypto | RESEARCH_REPLAY_REQUIRED | — | — | unknown after causal correction | NO_ESTIMATE |
| Alpaca monthly equities | SAFE_HOLD_PILOT | $1,140.90 | $971.14–$1,140.90 | bear 1/12; recent 10/24 | NOT_ADMISSIBLE |
| FX H4 candidate basket | RESEARCH | — | $1,007.34–$1,030.87 | not meaningful at 1-7 trades per variant | NOT_ADMISSIBLE |
| MPL / inplay next leg | RESEARCH_BLOCKED | — | — | unknown | NO_ESTIMATE |

The rows must not be added into a promised portfolio return: each has a different evidence grade and only ATT1 has current Bybit money authority. Alpaca remains a capped SAFE_HOLD pilot.

## Material progress

- MPL contract rebuilt to next-open, isolated input and write-once result before one-time holdout.
- Inplay +0.2352R result revoked because the simulator entered on the signal-bar close; next-open replay required.
- XSEC 7.5-9.5% research scenario revoked for the same same-close execution defect; causal contract added.
- XSEC modern metrics are quarantined; accepted scenario uses pre-holdout search only.
- Claude live env/try-except bug claims were not reproduced in the actual live state contract and were not patched.
- DOT live/backtest size parity: PASS.

## Next gates

1. Push immutable MPL commit, then one-time unseal — same session after explicit push authorization.
2. Finish and validate Alpaca 1000-name pool — hours for data; 1-2 days for repaired replay.
3. Funding-adjust XSEC and reconstruct closed-contract PIT universe — 2-5 engineering days, then shadow time.
4. Causal pre-holdout inplay replay — 1-2 engineering days; shadow only if it survives.
5. Accumulate clean ATT1 cohort — about 47 calendar days at observed frequency.

## Sources

- `reports/evidence/ATT1_DOT_ORDER_SIZE_PARITY_20260812.json`
- `reports/evidence/BYBIT_FUNDING_LISTINGS_ARCHIVE_VALIDATION_20260812.json`
- `research_lab/data/alpaca_pit_daily_v1/status.json`
- `runtime/orderbook/alt24_density_v2/heartbeat.json`
- `reports/research/alpaca_honest_diagnostic_v1_20260810/receipt.json`
- `research_lab/results/xsec_recount/xsec_recount.json`
- `research_lab/results/xsec_recount/symbol_holdout.json`
- `reports/research/fx_h4_annual_reproduction_20260810/summary.csv`
- `reports/research/six_day_crypto_pipeline_20260810/status.json`
