# Trading OS — production data / read-only shadow delivery, October17

**Money Lane and OS Lane progress concurrently.** This delivery implements the
owner's post-intake instruction; no new architectural review, LIVE policy,
financial authority, Brain judge or research outcome run. Exact published
research contracts07438fc/0efbca7 were verified before implementation.

## Alpaca P0 — DATA READY and server source/schedule operational PASS

Code commits: `ab68e36` Alpaca source/schedule, `9fcb4cb` IBIT DATA-ONLY,
`9177b75` Brain receiver. The receipt/document commit follows these components.

New components:

- `research_lab/alpaca_monthly_source_ops_v1.py`: full-universe source QA,
  calendar schedule, immutable source identity and own orders-OFF MonthlyBook.
- `scripts/run_alpaca_monthly_source_ops_v1.py`: default no-network verifier,
  explicit saved-source/public-fetch operation, fixed GET calendar capture,
  package pins, no financial/apply/owner-GO path.
- `deploy/systemd/alpaca-monthly-source-ops.service` and `.timer`: exact installed units.

Actual Mac capture fetched **all57 frozen tickers+SPY** with the unchanged
reference Yahoo1h/RTH/unadjusted loader, not a substituted daily source.58/58
have latest completed session **2026-10-16**,501 daily bars each and complete
expected RTH timestamps across the latest200 broker-calendar sessions. No
interpolation or current partial day. One fetch took34.170s. Source hashes,
full per-name coverage and real broker calendar are retained in
[actual data receipt](evidence/trading_os_data_shadow_20261017/alpaca_actual_data.json).

Installed separate37-file source package:
`/opt/bybot-research/alpaca-monthly-source-ops-20261017`.
Spec SHA256 `73b37f25da947e16a905bac1c59ed86a2230a47fe467694246ae2c1dfa2b5154`.
Original reviewed MonthlyV3 remains byte-identical and financially disabled.
The new package uses a separate source/book runtime, never adopts current NET.

Actual new timer is enabled/active, next19 Oct17:20UTC (13:20NewYork).
It checks broker calendar at13:20 and16:20NewYork: normal-session13:20 is NOT_DUE;
half-day13:20 collects the completed13:00 close; normal16:20 collects16:00.
The same calendar decides month-end selection and next-session effective stop
intentions. No fixed UTC offset; Nov2 opening remains14:30UTC/16:30Cyprus.
Repeated successful session never recaptures/reselects it. A missed month-end
cannot silently create a late entry.

An actual VPS full-universe bootstrap, including calendarGET/public capture/
source QA/own book binding, returned **ORDERS_OFF_OPERATIONAL_PASS**. Its own
book has no monthly positions, so daily maintenance honestly reports
`NO_OWNED_MONTHLY_POSITIONS`. Existing native ratchet/rearm behavior is exercised
by focused fixture tests; no monetary maintenance was activated for V3.
[Installation](evidence/trading_os_data_shadow_20261017/alpaca_source_installation.json),
[server bootstrap](evidence/trading_os_data_shadow_20261017/alpaca_server_bootstrap.json),
[37-file source manifest](evidence/trading_os_data_shadow_20261017/alpaca_source_package.json).

Root-cause/regression: the NET observer's calendar reader intentionally permits
same-day queries only. Reusing `.get()` for a760-day source warmup was refused
before network dispatch. The new source worker constructs its own fixed GET
calendar-range request through the existing redirect/size/timeout transport;
the deployed NET reader/allowlist is unchanged. A RED→GREEN regression verifies
the request method/route and absence of an order payload.

Remaining monetary gates are unchanged: actual30 Oct closed-source selection,
31 Oct independent decision/source check,1 Nov separate OWNER GO and exact
native binding/ownership, then permitted2 Nov opening. No future source readiness,
actual30 Oct selection, real daily stop update or strategy profitability is
claimed from today's operational PASS.

## IBIT P1 — implemented DATA-ONLY saved-source adapter

Published contract07438fc v1.1 replaces the four ambiguous v1 clauses. Exact
frozen event-source bytes are vendored unchanged with rule SHA256
`48d57d4ca06dbfe634e22c2435f1d2c1ddff83d18f8ea9fe95858c1987c48906`.
Only its function AST is evaluated against supplied in-memory source rows;
research filesystem loaders/main/outcomes never execute.

`research_lab/ibit_btc_data_only_v1.py` and the saved-source CLI implement SIP
daily provenance, raw bar timestamp vs calendar close, exact integer UTC-ms
alongside ISO timestamps, Binance+Bybit fixed15–16NewYork reference, half-day
NO_SEND, freshness and missing/defect handling. Full canonical raw hashes,
immutable first receipt, one decision/session, separate append-only Massive QA,
restart/tail recovery and alias/foreign-root protections are implemented.

The CLI defaults `NO_NETWORK`. This is a completed **saved-source adapter**;
an actual network collector/periodic IBIT source has **not** been deployed.
Receive timestamps remain caller-provided evidence. No actual Claude-shadow
comparison, SIP entitlement/latency proof or10-session acceptance is claimed.
Every output remains NO_SEND/orders_enabled=false; data_eligible is a diagnostic.
**39 targeted tests PASS**, including exact discrepancy boundary, first-receipt
recovery, half day, frozen-formula synthetic parity and outside-file preservation.

## Brain P1 — existing producer → common read-only receiver

`research_lab/brain_shadow_readonly_bridge_v1.py` and the import CLI reuse the
existing ShadowJournal lock/fsync/hash-chain/restart primitives. They do not run
another Brain, scorer, Risk Engine or allocator. Producer opportunities/context/
decisions are verified and mapped to SHADOW_PROPOSAL envelopes; broker execution
and financial accounting authority remain false. No joins/outcome file is read.

Actual producer fields `constraints/t_recorded_ms` map explicitly to the prose
contract's `reasons/ts`, plus pinned brain_version/policy/source/context hashes.
HEDGE/CONFLICT/INDEPENDENT metadata stays separate from the action. Missing
relationship stays UNKNOWN; no universal opposite-position veto is invented.
The frozen producer's all-ELDER-as-hedge behavior is not changed or endorsed.

Real source journals are28.5MB/25.5MB, larger than the first receiver bound.
The implementation now streams and verifies complete chains up to128MiB/250k
rows and imports only decisions at/after the explicit intake epoch
**17 Oct13:20:05UTC**. Exact receiver capacity is checked before the first append;
no partial batch if its bound is insufficient. **32 tests PASS**, including a
two-sleeve Context→decision→receiver roundtrip (synthetic) and >8MiB source.

Actual source-chain verification passed, but there are **0 post-intake decisions**.
Inspected source has20914 decisions each for BASELINE_V1/BRAIN_V1/HEDGE_V1,
latest11:51:01UTC; no BRAIN_V2_DET row was found. Therefore real V2 end-to-end
execution is **AWAIT_PRODUCER_EVENT**, not PASS. No old decisions were imported
to fabricate a new cycle. Context availability is SOURCE_TIMESTAMPS_ONLY;
per-feature provenance/quality and research policy usefulness remain separate.
[Actual import status](evidence/trading_os_data_shadow_20261017/brain_actual_import.json),
[source metadata](evidence/trading_os_data_shadow_20261017/brain_source_metadata.json).

## Verification / preservation

New-components combined run:85PASS; after one added two-sleeve verification,
final Brain32PASS. By component: Alpaca source15, IBIT39, Brain32. Existing
Alpaca source/book/native+initial Brain focused run72PASS. Full suite:
**5474PASS/60FAIL**, all60 failure names match the earlier baseline, no new names.
The final capacity/boundary delta is covered by targeted tests; the broad suite
is not declared green. [Exact commands/failure names/limits](evidence/trading_os_data_shadow_20261017/verification.json).

Bare full-suite tests appended four rows to the pre-existing local untracked
allowlist log. The exact original12-row prefix was reconstructed only after
matching the earlier frozen SHA256; four own test rows were archived privately
and removed. Original SHA365ff7d6…cc2e0e restored, no unrelated history removed.
Future broad runs must use the existing foreign-file guard wrapper.

Final13:40:47UTC independent broker/runtime readback: KITY samePID2440673,
ORDERS_OFF/flat0/open0/one unclaimed policy,23+155 pins match; NET still
0.325167779, DAYexpired277.69/openorders0, HALT/95pins and reviewed32V3 sources
intact. New37 source files match, timer active and server receipt verified.
**Broker writes0, financial units changed0, notifications0.** Only the new
isolated data units were installed/activated. Root review only; no independent
financial signoff or new money authority.
[Final readback](evidence/trading_os_data_shadow_20261017/final_runtime_readback.json).

## Next gates / delta prepared for Claude

```text
CODEX DELTA17.10:
P0 Alpaca DATA_READY:57+SPY, actual latest16.10,200-session completeness PASS.
Separate37-file source/schedule ACTIVE ORDERSOFF; actual VPS bootstrap operationalPASS.
Current NET/V3/KITY financial writers untouched; NET actual DAY rearm19.10 remainsOPEN.
KITY actual10/10 stillOPEN: existing personal micro policy unclaimed at13:40UTC.
IBIT07438fc adapter implemented/39testsPASS; saved-source only, collector/10sessions pending.
Brain0efbca7 receiver implemented/32testsPASS, full real chains verified.
Actual journal last11:51UTC: only three old policies, no V2/post-intake decision;
please verify the existing producer's actual V2 pass, no second Brain/restart by Codex.
constraints/t_recorded_ms aliases mapped; relationship remainsUNKNOWN unless explicit.
No policy/risk/order change or outcome/judge run. Money and OS lanes remain parallel.
```

Delta is prepared for the user/Claude; no message sent or Claude process changed.
