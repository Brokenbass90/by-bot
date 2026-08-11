# Six-day crypto matrix — data-quality and research verdict

Checked at `2026-08-11 06:36 UTC`. Scope is research-only; no private API,
broker calls, order authority or capital promotion.

## Matrix integrity

- intended grain: `3 windows × 8 families × 2 cost scenarios = 48 cases`;
- terminal receipt: `complete`, `48/48`, `failed_cases=[]`;
- summary: `48` rows plus header, all case keys unique;
- append-only ledger: `88 case_complete` events but only `48` unique case keys;
  the extra `40` are reused-case receipts from the repair resume;
- ledger retains `8` historical `case_failed` events from the zero-width defect;
  they are incident history, not current terminal failures;
- coverage: discovery `27/27`, replication `30/30`, OOS `30/30`, every selected
  symbol at `100%` bar coverage and zero reported gaps;
- reserved holdout `2025-10..2026-06` was not read;
- universe is current-survivor/turnover biased, not point-in-time. Promotion is
  forbidden even if a row were positive.

## Economic findings

| Family | Cases | Trades | Aggregate netR | Finding |
|---|---:|---:|---:|---|
| ATT1 current short | 6 | 0 | 0.00 | reachability/wiring failure; audit nonzero in all cases |
| ATT1 shallow short | 6 | 0 | 0.00 | reachability/wiring failure; no strategy verdict |
| Horizontal break long | 6 | 0 | 0.00 | reachability/wiring failure |
| Horizontal break short | 6 | 0 | 0.00 | reachability/wiring failure |
| Support reclaim strict | 6 | 446 | -77.27 | weak discovery plus vanishes and reverses |
| Support reclaim relaxed | 6 | 472 | -91.88 | weak discovery plus vanishes and reverses |
| Squeeze breakout long | 6 | 6,222 | -1,684.50 | consistently and strongly negative |
| Squeeze breakout short | 6 | 6,754 | -1,418.10 | consistently and strongly negative |

Support reclaim discovery was only `+5.04R` base / `+1.01R` stress for strict
and `+4.64R` / `+0.51R` for relaxed, with `|t| <= 0.38`. Both variants became
negative in replication and worse in OOS. This is not a candidate.

Squeeze was negative in every window, direction and cost scenario. The repaired
first missing case alone was `620` trades, `-131.34R`, `-0.21184R/trade`,
`t=-6.74`, PF `0.537`; OOS long/short were also strongly negative. The current
squeeze mechanism should be archived as economically rejected, not tuned.

## Decision

1. Promote none of these rows to shadow/canary/money.
2. ATT1/horizontal zero-trade rows require a liveness and adapter trace before
   they can inform strategy quality. A zero-trade harness result is not proof
   that the live/manual setup is dead.
3. Archive current squeeze formulation with its defect and repaired evidence.
4. Do not spend the reserved holdout on parameter repair. A second crypto leg
   needs a new causal mechanism or independently traced implementation.

Primary evidence:

- `reports/research/six_day_crypto_pipeline_20260810/status.json`;
- `reports/research/six_day_crypto_pipeline_20260810/summary.csv`;
- `reports/research/six_day_crypto_pipeline_20260810/ledger.jsonl`;
- `reports/research/six_day_crypto_pipeline_20260810/coverage/`.
