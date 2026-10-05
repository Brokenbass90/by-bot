# KITY M3 Orders-OFF Implementation Plan

> **For agentic workers:** Use executing-plans/TDD; primary owns financial logic, one bounded financial review. Mechanical public-I/O work may be delegated under AGENTS routing.

**Goal:** Implement an isolated frozen-signal reconstructor and ten-leg public execution assessor, with deterministic orders-OFF receipts and exact blockers.
**Architecture:** Pure source validation/ranking/sizing/depth/cost functions plus a public GET/file CLI. No existing trading modules or production state imported. Raw captures are hash-bound; all account/money readiness stays explicitly blocked.
**Tech Stack:** Python standard library, Decimal/Fraction, pytest. Existing recovery branch/checkout; no dependencies or new worktree.
**Spec:** docs/superpowers/specs/2026-10-05-kity-m3-orders-off-design.md, owner approved for implementation October5.

## Global Constraints

- Exact pinned research refd6ed812; no judge/archive/holdout rerun or strategy changes.
- Frozen n//10, top50 OI exactly d−1 23:55UTC, ≥60 closed bars, n≥30, Thursday grid, seven-day holding, research benchmark12bps.
- Requested production basket5long+5short; smaller frozen basket is emitted, then BLOCKED_EXECUTION, never padded.
- Common ten-book assessment clock, maximum2seconds source age including declared clock uncertainty and receive-to-use delay. Missing Bybit CTS is UNKNOWN.
- No credentials, broker/private endpoint, order sender, live imports/config/routes/schedulers or production/VPS changes.
- Public evidence contracts cannot authenticate a selected account or establish future funding/price hard bounds.
- Atomic create-exclusive receipts; same exact request returns original result, conflicting identity fails closed.
- Preserve foreign allowlist, Alpaca and ATT1 probes/deadline. Separate owner GO before money.

## Review Focus

- Incomplete OI census/ambiguous listing dates must block ranking; short/missing candle data cannot silently rescue top50.
- Precision ties and string/int/bool/NaN schema attacks must not change frozen selector or bypass dates/caps.
- Ten independently fresh snapshots can be stale at common time; missing CTS/clock uncertainty blocks.
- Equal symbol names do not prove equivalent base asset/contract multiplier/venue funding portability.
- Crashes, symlinks and competing receipt writers must not overwrite or credit a second intent; external artifact hashes are consistency, not origin authentication.

### Task 1: Pure frozen reconstruction

Files: bot/kity_m3_orders_off.py; tests/test_kity_m3_orders_off.py.
Interfaces produced:
- `digest(value: dict) -> str`: canonical JSON SHA256, disallow NaN.
- `capture_payload(capture: dict, venue: str, endpoint: str) -> object`: validate venue/path/raw SHA/request/receive and parse raw JSON; no network.
- `reconstruct_signal(bundle: dict, now_ms: int) -> dict`: no exceptions for invalid evidence; terminal status/reasons, source pins, frozen basket/ratios, money flagsfalse.
Bundle keys: `day`, `research_ref`, `census` capture, `oi` map capture per census symbol, `klines` map per selected top50 symbol. Census `/fapi/v1/exchangeInfo` must be captured at cutoff: request≤receive≤cutoff and cutoff−receive≤2000; this limited public PIT snapshot convention is explicitly recorded, never historical listing proof from today's inventory. All eligible candidates at cutoff are included by onboard/delivery dates; inactive/ambiguous statuses relevant to cutoff block. Missing OI blocks whole census. Exact point/params, duplicate exact point reject. Zero published OI is legitimate ineligibility, not missing.
Candle fields0/6 times,7/10 volumes; unique ordered daily closed bars, lastdayd−1, 60history. A known new listing with<60 bars may be feature-ineligible; unexplained missing mature-history data blocks. Feature ranking follows original float division/tuple ordering; preserve raw values and record numeric ambiguity. Ratio must be finite/in[0,1]. No first unseen receipt before Oct8; signal evaluation pre-entry boundary (d+1 midnight), later diagnostic only.
- [x] Write tests requiring interface, then valid50/30/40, tie order, OI missing/2350/duplicate, late/future/current candle, duplicated bars, wrongref/date, mature incomplete/new listing, changed raw hash.
- [x] Run `.venv/bin/python -m pytest -q tests/test_kity_m3_orders_off.py`; Expected initial assertion failures on missing interface.
- [x] Implement functions with no live/network imports; source/data failuresBLOCKED_DATA, valid30/40 cardinalityBLOCKED_EXECUTION. Signal-only success status remainsBLOCKED_DATA, reasonEXECUTION_EVIDENCE_REQUIRED, signal_validtrue.
- [x] Same command; Expected all Task1 testsPASS.

### Task 2: Per-leg execution and deterministic accounting

Same module/tests; consume reconstruct result. Produced:
- `assess_execution(signal: dict, execution: dict, now_ms: int) -> dict`.
Execution keys: venue, instrumentscapture, books map, funding_info capture optional, `clock_uncertainty_ms`, `per_leg_notional_usdt`, `max_gross_notional_usdt`, optional scenario_costs (fee rates, funding_rate_envelope, settlements, sources/basis). Numeric scenario inputs are diagnostic proposed assumptions, never actual account evidence. A validated reconstructed signal and exact independent basket hash required; actual quantities floor to step, all10legs required, no rescue or substitutions. Enforce underlying equality/USDTlinearperp/status/positivefilters/minmax/fullbook coverage.
Books Binance `/fapi/v1/depth` useT; Bybit `/v5/market/orderbook` usects; raw endpoint/symbol params matching. Allsource+receive times≤common now (within supported declared clock uncertainty), worstsourceage≤2000, complete ascendingasks/descendingbids/noncrossed books; duplicatelevels reject. For each leg compute actual entryVWAP/exitVWAP simulation at exact quantity, side-correct current spread/roundtrip mark-neutral cost, source hashes, depth coverage, diagnostic minimum and common basketfloor, rounding deviations.
Perleg roundtrip fee/slippage/funding scenarios weighted by exact notional; fixed research12bps shown separately. Missing accountfee/fundingpolicy meansBLOCKED_DATA even when minima/books pass. Infeasible filter/depth/cap meansBLOCKED_EXECUTION. No public combination returnsREADY_FOR_CANARY. Bybit portability always requires separate actual-basket price/funding evidence.
- [x] Tests: quantityfloor rejects vs min, no grosscap increase, marketmax/filters/mapping, shallowdepth, common-time stale/missingCTS/unknownclock, fee weighted arithmetic, holdfundingliability, shape attacks, mutatedsignalhash.
- [x] RED then implement exact Decimal/Fraction math then GREEN targeted suite.
- [x] Add `reconcile_paper_events(signal, events) -> dict`: synthetic only, stableevent/executionIDs, dedup identical/rejectconflicts, independent10legpositions/fees/funding, partial/unknown terminal liabilities block. No brokercommands/protection fabrication. Tests partialfill/reject/rotation/duplicate/missing/restart/finality; GREEN.

### Task 3: Public collector, external comparison and receipts

Files: scripts/kity_m3_orders_off.py; tests/test_kity_m3_orders_off_cli.py.
Consumed core functions above. Produced:
- public `get_public(venue, endpoint, params)` captures raw UTF8/sha/request/receive; strict endpoint/param allowlist, timeout/size/request limits, redirect reject; no environment credential loading.
- CLI commands `reconstruct --bundle FILE`, `assess --signal FILE --execution FILE`, `compare-forward --bundle FILE --forward-dir DIR`, `capture --venue VENUE --endpoint ENDPOINT --params JSON --output FILE`, `publish --receipt FILE --runtime DIR --identity NAME`.
- `compare_forward(bundle, forward_dir, now_ms)` reconstructs independently from caller's raw capture bundle, validates external declared source file hashes/paths/date/ref/completebasket; retains raw external document/hash, never executes its code. Historical current Claude forward lacks raw wireprovenance; compare can prove only derivedfile consistency/basketmatch, statusBLOCKED_DATA for missing causalraw provenance.
- `publish_receipt(runtime, identity, receipt)` holds file lock, rejects existingunsafe/symlink path, canonical exact identity/ref/day/content consistency, write/fsync/temp+atomic hardlink create-exclusive, replay byte-identical original receipt; no extraintent for rerun. Testconcurrency/conflict/tamper/crash incomplete.
- [x] Write tests -> RED interfaces; implement allowlistedGET/fileCLI/immutablepublisher -> GREEN. CLI output moneyflagsfalse, no activationflag, malformed inputs explicitstatus/error and nonzeroexit; standardBLOCKED receipts are valid successful CLI executions.

### Task 4: Integration evidence, bounded review and delivery

- [x] Primary reconstruct synthetic50 sourcebundle and exercise CLI/core end-to-end with immutable receipts; malformed external source/census alwaysblocks.
- [x] Bounded public diagnostic depth/filter feasibility for10 explicitlyNOT_A_SIGNAL names on Binance/Bybit; no hypothetical filled terminals or futurebasket credited; common2s mayhonestlyblock. Preserve rawcapturehashes, actual partial failures, declared fees separate.
- [x] Run combined KITY tests + appropriate ATT1/Alpaca isolation tests; once fullpytest, compare known57baseline failures from checkpoint. No unrelated fixes to forcefullsuitegreen.
- [x] One independent6-astra/high finalfinancial/security review; one boundedfixpass with regression RED→GREEN; recordlimitations, no repeatedreview/quotaretry.
- [x] Publish runbook/readinessreceipt exactdata/execution blockers, updatecanonicalhandbook/roadmap and specapprovalstate. Scopedcommit/push, verifyremote; foreignhashunchanged.

## Completion contract

Implemented callable orders-OFF candidate, passing meaningful tests, reproducible CLI receipts/venue diagnostic, all missing actual/future evidence labelled. No deployedservice orNEWmoney authority. FirstunseenOct8 preserved; remaining capital decisions get a complete source-bound dossier later.

## Delivery rulings

Owner implementation approval was explicit; no repeat permission gate. The
candidate stays local without scheduler, credentials or sender. Task3 publication
was narrowed to typed accepted signal receipts with one derived weekly identity;
execution evidence is returned separately and carries its full raw bundle.

One implementation review returned BLOCKED_FIX_REQUIRED. All seven important
and one minor findings were repaired by primary and regression-tested, with no
second independent signoff claim. Declined review scopes were retained as
explicit blockers or out-of-scope research/production boundaries: frozen judge,
actual account/money runner, deployment health, future funding hard bounds,
Bybit portability, origin authentication, one-snapshot capacity/adverse movement,
diagnostic target versus actual caps. Conservative source/filter refusals and
frozen float ranking remain. Formatting/broad refactoring is deferred.

95 targeted PASS; full3618PASS/57exact oldFAIL, no new/removed failure names.
One additional standalone CLI test follows full-suite collection. Synthetic
lifecycle is prepared-quantity/source-bound and preserves known prefix exposure.
Source hashes/repeated immutable publication and old-book refusal verified by
actual CLI. Public25GET diagnostic is NOT_A_MARKET_SIGNAL/NO_FILL_SIMULATIONS;
no unseen week or selected-account evidence is fabricated. Scoped publication
receipt is written privately after commit/push verification.
