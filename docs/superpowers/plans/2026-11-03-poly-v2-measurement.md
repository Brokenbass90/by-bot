# Polymarket V2 read-only measurement implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. Preserve the accepted live repairs and source evidence.

**Goal:** Measure explicitly supplied V2 signals against the selected token's real ask ladder without wallet, signing, orders or an economic promotion.
**Architecture:** One pure function in the existing research_lab and a file-only CLI. No new collector, daemon, generic bus or portfolio engine. The original rule stays with Claude; an independent source replay reconciles the20 published observations.
**Tech Stack:** Python3.12 standard library, pytest.
**Spec:** Owner's3Nov instructions and read-only copy of Claude ZADANIE_CODEX_POLY_V2_ISPOLNITEL_2026_11_03.md. Latest owner amendment: historicalFAIL retained; ORDERS_OFF measurement only. New score model not integrated.

## Global constraints

- No keys/wallet/network/financial constructors/orders/GO/risk changes.
- Keep original20/19matches separate from historical2121/840 result; no judge run or rewritten evidence.
- Only actual selected-token asks; no1−bid; depth stops at0.985; $100 is a model amount, never an approved money allocation.
- Explicit receive timestamps/sourceSHA/policySHA and continuity; missing fees/status/time become UNKNOWN, never zero or invented fill.
- Fee estimate from captured market rate: shares*rate*p*(1−p), each displayed level, rounded5decimals. This is an estimate, not actual matching/fees/PnL/capital release. Source https://docs.polymarket.com/trading/fees checked3Nov.
- OriginalV2 economicFAIL prevents TINY. Changing future model policy cannot silently change a measurement receipt.

## Review focus

Wrong NO token; depth beyond price limit; future/pre-request timestamps; missing fees falselyzero; outcome substituted for actual funds availability. Each gets a behavior test.

## Task1 — already published20 source audit

- [x] Snapshot completed newline prefixes and pinned source/prereg/task bytes, preserving source files.
- [x] Independently replay only the published20 observations, compare timestamps/outcomes/net.20/20 match;10 actualAask/10 syntheticBask; executionqualificationUNKNOWN20/20.
- [x] Preserve exact checks and hashes in private audit/public sanitized report, no sealed new outcomes.

## Task2 — measurement function and CLI

Files: research_lab/polymarket_v2_orders_off_v1.py; tests/test_polymarket_v2_orders_off_v1.py.
Interface: measure(signal,book,market,decision_ms)->strictJSONdict; join_outcome(receipt,winning_token,resolved_ms,joined_ms)->newdict. Signals supply market_id/token_id/policy_sha256/received_ms/model_price, not money authority. Books supply asset_id/bids/asks/received_ms/time_origin/continuity/source_sha256. Market supplies same market_id/tokens/accepting_orders/received_ms/source_sha256 and optional captured fee_rate/fee_source_sha256.
- [x] Write behavior tests and observe RED.
- [x] Implement selected-token ladder walk, timestamps/lineage, UNKNOWN reasons, displayed VWAP/fee/net estimates, strict no-order fields.
- [x] Add outcome join with parentSHA; resolution is not funds availability or strategyPnL.
- [x] File-only create-exclusive/fsync CLI; reject unknown/money command arguments.
- [x] Run focused measurement+existingWSdata/delivery tests, isolated network-denied real-capture measurement, bounded review and exact evidence.

## P0 dependency ruling

Monthly125 alreadyarmed; actualwindow14:30–14:35UTC, nativeGET14:40. No repeatedactivation.
PUMP sourceV3 only fixes physicalhandoff for acceptedpatch59f663: coldpreload147s vs previous120s timeout; bounded900/nextWSdeadline, oneclaim, originalfinancialowner. Nativequietboundary14UTC, actualpatched15UTC. Latest owner explicitly renews throughputrepair work after earlier originalDATArestoration; no new financialauthority. Review found timer-on-cleanup defect, fixed with3red→green tests.10local/same10VPSPASS, boundedreviewresolved. No claimedactualH1PASS untilnativeproof.

Actual local result:23newmeasurement+48WS=71PASS; oneboundedreview2findingsfixed4red→green. Actualsealedfullbook+causalpriorcatalogue replay networkdenied, UNKNOWNmissingfee/status. Runtimeadapter/regularsignals remainOPEN outside this localmeasurementtask.
