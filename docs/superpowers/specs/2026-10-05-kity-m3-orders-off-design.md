# KITY M3: frozen signal → execution evidence, orders OFF

Status: written specification for owner review; no implementation approval or money authority inferred.
Owner intent (October 5): after Alpaca re-arm, build the smallest useful KITY execution candidate before the first unseen October 8 signal. Use Claude's frozen research, preserve ATT1 probes, avoid broad merges or Factory rewrites. Success is reproducible execution readiness or a precise blocker, not a promised LIVE date.

## Scope and choice

This is a new basket execution subsystem. Build a small isolated public-data/evidence path, not a replacement trading framework. It must have no credential loader, order sender, broker writes, paid AI calls, or live configuration hooks. Existing ATT1 and Alpaca owners/state remain separate. A future money runner is outside this specification.

Three approaches were considered:

1. Use Binance signal and Binance execution: least venue portability uncertainty, but selected-account eligibility, actual costs and minimum sizes are not yet established.
2. Use Binance signal and Bybit execution: existing account infrastructure may help later, but symbol equality alone cannot establish price/funding portability or safe concurrent ownership.
3. Import Claude's paper script as production: fastest copy, but insufficient causal source retention, cardinality enforcement, quantity validation and restart evidence.

Recommend an independent orders-OFF consumer and public execution assessor. Produce separate Binance and Bybit assessments from the same sealed signal; leave venue selection explicitly unresolved until evidence supports it. Do not assume one account's credentials, mode, fee tier or cash apply to the other.

## Immutable source contract

Authoritative research ref: `research/fabrika-v1@d6ed8126c041969de0bc6191e39fefe4a1272d5b`, verified on origin October 5. Pin prereg, judge, packet, forward code/runbook and receipt separately by Git blob and SHA256. The historical verdict remains READY_FOR_BUILD. PRIMARY 194 weeks and replication SAME_SIGN are declared frozen research outputs; this delivery does not independently rerun or certify the judge/raw archive.

The actual prereg/judge use `k=n//10`, with n≥30 and top50. Therefore 30–39 feature-valid names yield 3+3, 40–49 yield 4+4, and 50 yield 5+5. Packet prose and current owner's production brief require 5+5. Keep the frozen selector unchanged; emit the exact frozen basket even when its count is below ten. The requested ten-leg production candidate must then report `BLOCKED_EXECUTION` with reason `BLOCKED_BASKET_CONTRACT`, not add names, expand the universe, substitute symbols or silently rescale weights. This is an explicit compatibility decision visible in the dossier, not a rewrite of research.

Signal:
- UTC Thursdays on the grid starting 2021-07-01.
- PIT top50 Binance USD-M USDT perpetuals by OI value at exactly d−1 23:55 UTC, then frozen feature/history eligibility. Exact raw OI point required; earlier-point fallback is not exact evidence. Preserve a source-bound candidate census at that cutoff, including listing/status transitions and one explicit OI outcome per candidate. Missing OI for any potential top50 constituent blocks the whole decision unless retained evidence proves it cannot enter top50; rank over the successfully returned subset is insufficient. A present-day active-contract list cannot by itself certify historical eligibility. Feature ineligibility is assessed only after the complete top50 is fixed, and never repairs missing universe data.
- Taker ratio from a closed d−1 daily kline, fields 10/7; 60 closed historical bars required, finite valid volumes, no duplicate timestamps, no current-day feature.
- Keep frozen feature/symbol ranking and tie order; preserve raw numeric source precision. Judge OI tuple order is descending `(OI,symbol)`; any forward mismatch at the top50 boundary must be explicit.
- Equal weight frozen deciles, seven-day close-to-close holding and frozen research cost12bps+Binance funding. Neither changed strategy nor a new stop/early-exit rule is approved here.

Closed-day timing matters: first signal is October8 00:05UTC; paper entry reference is October8 close, available October9 00:05UTC; first exit reference is October15 close, available October16 00:05UTC. A next-day historical close is a paper valuation, never an executable fill. Public execution observations at receipt time must be reported separately, with latency and price differences.

## Components and boundaries

Proposed files for the later reviewed implementation plan:
- `bot/kity_m3_orders_off.py`: pure frozen-source validation, selector and typed evidence/intent output. No network or live imports. Raw source numbers retained; Decimal for sizing/costs. Selector parity against synthetic ties/boundaries is required; incompatible numeric ambiguity blocks.
- `scripts/kity_m3_orders_off.py`: allowlisted public GET capture and external-evidence ingestion into a separate KITY runtime directory; no access to Claude's writer directory or live databases. No scheduler/cron installation in the initial local delivery.
- `tests/test_kity_m3_orders_off.py`: causal/contract/minimum/cost/idempotency fixtures; no judge execution or research-outcome mining.
- `reports/KITY_M3_*`: source pins, verdict, limitations, next exact evidence requirements and runbook.

Public capture records endpoint/query, request-start, receive time, raw response hash and source timestamps/sequence where published. Missing freshness information remains UNKNOWN. A quiet book or recent local write does not establish market freshness. Preserve the project's two-second execution observation gate; no threshold relaxation. Evaluate all ten legs against one persisted basket-assessment timestamp, with supported source clocks and clock uncertainty plus receive-to-use age; all ten must satisfy the gate together. Independently fresh-at-receipt sequential quotes do not establish simultaneous basket feasibility and remain diagnostic only. Historical closed candles and OI snapshots have their own exact date identity rather than pretending to be current books.

Freeze the first accepted October8 signal by create-exclusive/atomic publication with a single KITY evidence writer and content hashes. Existing payloads must be revalidated, not blindly read as trusted. A changed date/ref/source prefix or malformed/incomplete file fails closed. For prospective paper eligibility, actual source availability and sealing must both precede the frozen entry-close boundary: October9 00:00UTC for d=October8, generally start of d+1 UTC. Retain both times across replay. A late reconstruction is retrospective diagnostic evidence and cannot repair a missed prospective week. Retries before that boundary can gather missing evidence but cannot replace an already sealed decision or claim earlier timestamps. A crash before completion yields an incomplete capture, not a completed lifecycle.

Record stable week, signal hash, venue and basket identity in inert intent IDs. Repeated runs do not create a second intent or simulate another fill. There is no `send_orders` switch or activation route in this component. Do not import a dormant sender simply because it is normally disabled.

External Claude forward files are evidence candidates, not authority. Validate exact prereg/ref/date/basket/source hashes, independently reconstruct the frozen expectation from raw public inputs, and compare all legs. Never execute `--shag`, start another writer in Claude's state directory or modify the research branch. Preserve the original receipt even if comparison fails.

## Venue, quantity and cost assessment

Assess every selected leg independently: active linear USDT perpetual contract, exact symbol/underlying mapping, positive valid lot/market-lot/price/notional filters, maximum market quantity and funding interval. No missing-filter default0, symbol replacement or guessed redenomination. If any leg is missing, prelisting, ambiguous or delisted, block the entire proposed basket and preserve the reason.

Report the minimum reference quantity and gross notional for each leg and the common equal-notional basket floor. Diagnostic ceiling to exchange minimum is permitted only in the feasibility table and clearly marked NOT_ADMITTED_QUANTITY. Actual owner-capped sizing floors to the step and rejects any infeasible leg; it never rounds upward to rescue a trade. Report residual weight error; owner-reviewed tolerance is required before money readiness. Gross notional is not cash/margin or worst loss, and leverage cannot be invented to make it fit.

Measure actual candidate buy/sell L2 VWAP, full depth coverage, spread, observed latency and adverse movement in a bounded public sample at the intended quantity. One ticker does not prove capacity. Thin names and short squeezes require account/capacity/concentration evidence; do not promote an execution candidate merely because ten minimum lots fit.

Frozen12bps is the historical benchmark. Compute venue-specific entry+exit fees, spread/slippage and funding separately. Total round-trip cost is a notional-weighted sum over all ten legs, not `10×12bps` of the basket. Funding cash uses signed quantity and settlement mark/notional plus explicit unresolved liability; a sum of rates at assumed constant notional is labelled synthetic. Historical Binance funding does not stand in for Bybit funding.

Do not reduce fees/reserves, shorten hold, invent an absolute risk cap, or import ATT1 R/D values. Required dossier fields include selected account's authoritative fee tier, cash/margin/mode, simultaneous sleeve ownership, fixed absolute per-leg/portfolio/daily caps, funding liability and emergency/partial-basket unwind policy. Until these are defined and source-bound, `READY_FOR_CANARY` is impossible even if public calculations pass.

For Bybit, a separate public price/funding portability assessment of the actual ten symbols is required. Matching symbols and one correlated quote pair do not prove the signal edge transfers. No new strategy judge, sealed holdout consumption or money experiment is included here.

## Paper lifecycle and failure coverage

Pure replay uses synthetic broker events only. Exercise ten-leg prepare, partial fill, rejection, missing/duplicate/out-of-order events, restart at each boundary, weekly rotation/close-before-new-open, funding and terminal reconciliation. Report remaining exposure and unknown liabilities explicitly. A simulated partial basket cannot be silently labelled balanced or fully protected.

Any hypothetical money/protection path remains a design requirement in the dossier, not an implemented live sender. Native account-specific protection, exit ownership, timeout/unwind and finality must be validated before later promotion. Do not install directional stops that alter the frozen seven-day strategy without separately reviewed evidence.

Delisting/missing-price research uses the frozen last-close proxy; execution must label that unexecutable proxy and block/escalate unknown exit exposure. Never manufacture a fill at the last observed close or count partial available outcomes as a complete terminal. Paper and real cost/finality receipts must remain distinguishable.

## Acceptance and verdicts

Local candidate acceptance requires frozen-source pins, synthetic selector parity, exact date/causality, whole-basket contract checks, per-symbol Decimal minimums, unknown/filter rejection, two-second book checks, no sender/import/credentials, atomic/idempotent records and explicit incomplete/partial lifecycle accounting.

Before October8: `BLOCKED_DATA: FIRST_UNSEEN_SIGNAL_NOT_DUE` is expected. Source-contract defects are separate findings, not evidence that the historical strategy is killed. Public venue inventory can reduce uncertainty now; actual basket economics cannot be asserted before the basket exists.

Final promotion dossier uses only:
- `BLOCKED_DATA`: missing/invalid source, unavailable actual signal/account/cost/finality evidence.
- `BLOCKED_EXECUTION`: identified venue minimum/portability/whole-basket/capacity/contract failure under frozen rules.
- `READY_FOR_CANARY`: all public and selected-account acceptance evidence complete, with fresh proposed caps, exact ownership/protection/exit/finality and rollback dossier. This means eligible for separate owner review, never permission to trade.

Owner GO remains separate. No calendar promise for October15/22. ATT1 retains its independent 2–3 clean filled terminals/net-R, fresh actual dossier and GO gates. Original probes/deadline October6 14:12:25UTC are unchanged.

## Claude's highest-value parallel contribution

Provide a machine-readable frozen contract/registry and source-bound test vectors without rerunning the judge. Before October8, make forward evidence preserve raw OI/kline/entry/exit/funding replies with request/receive timestamps, atomic immutable output and explicit n//10 basket count. Exact23:55 absence must be UNKNOWN; do not retune eligibility to force ten legs. Distinguish benchmark close-based paper prices from current executable observations.

Supply a current read-only forward runtime path/process/heartbeat receipt and first-signal source prefix. Codex consumes that evidence; no unverified claim of a healthy daemon is accepted. Keep TOLPA in background; after this handoff, one independent long mechanism, then one range mechanism through Factory with WIP1, causal data, costs/minimum feasibility, frozen falsification/holdout and terminal judge. Improve that one Factory end-to-end acceptance cycle before broad automation or repository cleanup.

## Specification review record

One bounded `gpt-6-astra/high` financial/security review identified three must-fix gaps: missing-OI universe completeness, late reconstruction credited as prospective, and lack of a common ten-book freshness timestamp. The primary incorporated all three requirements and aligned basket-contract reason with the three terminal status values. This is a specification review, not implementation signoff or money approval; no second review is claimed.
