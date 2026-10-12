# Brain V2 A3/A4 local research runbook

Current delivery: `BRAIN_V2_A3_A4_ORDERS_OFF_DELIVERY_2026_10_12.md`. This is a pure
supplied-source assessor and bounded journal, not an autonomous worker.

1. Verify the seven source hashes against
   `evidence/brain_v2_a3_20261012/source_manifest.json`; active table is A2
   35fa0e08…7020. A1/old table and all old receipts remain historical evidence.
2. Use a new owned absolute real-path journal directory with `brain_v2_a3.BrainJournal`.
   Never adopt an A1/V1/OS2 directory, truncate corruption or retry a poisoned
   writer. INIT requires sourced positive equal starting arm capital, known
   positions/protection and epoch on15m grid at/after table cutoff. Actual start
   also requires table/source publication identity; cutoff alone is insufficient.
3. Supply every sequential TICK including empty ticks. `tick_ms`, `known_at_ms`
   and `coverage_end_ms` must agree; `batch_complete` and `terminals_complete`
   explicitly prove supplied populations. Exact opportunity time mapping uses
   A2, cost_model_id `BRAIN_V2_A3_STREAM_R_NET6BP_2BP_BYBIT_FUNDING`.
   Preserve original signals/universe/stops/hold; don't relabel unknown sources
   as complete. Off-grid rejection must not be rounded to another package.
4. `contexts` reuse A1/A2 envelopes at floor(tick)/hour from closed data only;
   UNKNOWN context falls back to pinned sleeve μ. `entries` for each opportunity
   contain exactly lev/source_hash/t_available/entry_rule, source-bound to its
   original stream, next_open. No R/hours/future exit in entry metadata.
5. Provide terminal events on the scheduled tick: opportunity_id, original
   integer hours, R, source_hash, available_ms, cost_model_id, funding. The
   assessor derives release=entry+hours*1h. Serial replay cannot accept a late
   terminal and overwrite earlier realized E; source failure is BLOCKED_DATA.
6. Funding envelope schema `BRAIN_V2_A3_FUNDING`: Bybit symbol, archive source
   hash, calendar hash/completeness, exact start/end and known-at time, expected
   sorted unique settlements and rates with settlement/availability times.
   Derive the calendar from authoritative symbol/period evidence; never use
   current interval metadata as universal historical proof. Rate timestamps
   strictly entry<t<=release; availability after release means missing at exit.
   Actual bytes must be retained externally; hashes/booleans in a synthetic
   request do not authenticate a feed or broker.
7. A4 UNKNOWN terminal is freed normally with all cash components null; no
   partial or zero PnL. Only KNOWN cash changes E. Late rate is not a new terminal
   and cannot re-credit E. `funding_coverage` reports independent arm counts,
   unknown slot-hours/risk and >5% BLOCKED_DATA. A pending zero population is not
   a PASS. No coverage result changes strategy admission; developing judge is
   separate and remains NOT_RUN.
8. Inspect status and each arm decision/closed ledger; persisted BLOCKED_DATA
   leaves state unchanged. Request-ID payload conflict is not a retry channel.
   Journal reopening verifies chain and full semantic replay; uncertain append
   must reconcile from the original root. Limits remain OS2 bounds (8MiB total,
   2MiB input/receipt,4096 receipts). Reviewed retention is required before an
   actual ongoing shadow; do not reset the epoch to avoid a bound.

Local verification from repository root:

```sh
.venv/bin/python -m pytest -q tests/test_brain_v2_a3_ticks.py tests/test_brain_v2_a3_review_regressions.py
PYTHONPATH=. .venv/bin/python reports/evidence/brain_v2_a3_20261012/generate_synthetic_receipts.py
```

The second command generates **synthetic** evidence only, never the research
train table, market streams or judge. Actual four-fold filter/shadow/money gates
remain outside this delivery. No deployment, credentials or order authority.
