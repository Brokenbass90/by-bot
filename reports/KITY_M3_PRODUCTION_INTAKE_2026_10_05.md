# KITY M3 production intake — October 5

Production verdict: **BLOCKED_DATA / orders OFF**. Frozen research is READY_FOR_BUILD; the production candidate is not implemented. This cycle completed source verification, synthetic forward-contract probes, full public venue filter inventory and a reviewed written specification. It did not run the judge or modify Claude's checkout.

Origin research ref was independently verified as `d6ed8126c041969de0bc6191e39fefe4a1272d5b`. Seven source artifacts are pinned by Git blob and SHA256. The declared result and KITY manifest SHA256 match their Git files; the large raw taker archive's hash is declared evidence, not independently recomputed or consumed here. Forward daemon health/path remains NOT_CONFIRMED; no current external runtime receipt was supplied.

Frozen prereg/judge explicitly use n//10 with n≥30. The requested5+5 production contract differs when fewer than50 features are valid. Synthetic source replay reproduced30→3/3,40→4/4,50→5/5; a6-leg paper receipt still says PASS. Other captured synthetic cases accept23:50 OI without23:55, an existing signal with wrong date, and60 duplicated bars. This does not invalidate the historical verdict; it prevents blindly importing the forward script as production. Exact original code was executed only with synthetic stubs/HTTP guard; zero network/judge calls in the fixture.

## Current venue inventory

Four public GETs at13:48:34–13:48:35UTC were retained with raw hashes. Binance525 eligible USDTperps: MIN_NOTIONAL50 forBTC only,20 for5,5 for519. Bybit782 active linear USDTperps,462 exact Binance symbol overlaps and63 missing; page cursor empty. Filters are symbol-specific, as documented by [Binance](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) and [Bybit](https://bybit-exchange.github.io/docs/v5/market/instrument).

BTC minimum0.001 at captured quotes gives ~$86 gross on both venues despite Binance's50/Bybit's5 minimum-notional filters. ETH reference minimum is ~$21.77 Binance/~$27.22 Bybit; LINK ~$20.14/~$5.63. These are ceiling-to-minimum diagnostic scenarios, **not admitted quantities**, actual future basket, total cash requirement or money readiness. No symbol is replaced or removed from the frozen signal. Ticker inventory is a single observation; L2 capacity, common-time10-leg freshness, costs/funding portability and account constraints are not proved.

## Exact next steps

Written specification: `docs/superpowers/specs/2026-10-05-kity-m3-orders-off-design.md`. One verified6-astra/high specification review found missing-OI universe completeness, late reconstruction eligibility and common-time basket freshness gaps. Primary incorporated all3; no second review or implementation signoff claimed. Mechanical workers'5.6-luna/medium settings were verified from runtime turn_context, not their requests alone.

The specification awaits owner review under brainstorming's written-spec gate. After approval, prepare the concrete implementation plan, then isolated orders-OFF candidate/tests. Preserve the first unseen October8 00:05UTC signal; benchmark entryOctober9 00:05UTC and first exitOctober16 00:05UTC are paper close references. Do not label them executable fills. Exact10-leg candidate must block variable smaller deciles rather than alter research.

Before any READY_FOR_CANARY claim: all actual basket legs, venue/source/cost/quantity/capacity/portability, selected-account caps/cash/mode/fees, ownership, protection, exit/finality and rollback evidence. A separate owner GO remains mandatory. No promised October15/22 activation.

Claude's useful parallel work: sealed machine-readable contract+registry/test vectors; raw timestamped OI/kline/entry/exit/funding responses, exact23:55 handling, atomic immutable forward records and a read-only runtime receipt. Do not rerun judge or retune n//10. Then one independent LONG mechanism followed by RANGE under WIP1, with costs/minimums/causality/holdout and terminal verdict. Codex does execution acceptance; Factory research stays Claude's responsibility. No message was sent to Claude.

Alpaca re-arm and first AMD exit lifecycle passed separately; final net remains pending delayed fees. ATT1 probes still RUNNING with original PIDs/NRestarts0 at13:40UTC and originalOctober6 14:12:25UTC deadline. No probe restart, deadline extension, LIVE transport or money-policy change. Last independently replayed ATT1 public cohort remains the08:19 snapshot:1 clean ADA terminal, simulation net-R−1.048963; no extra clean terminals credited here.

Reproduce the offline checks: `python3 .private/alpaca_rearm_20261005/accept.py`, `python3 .private/kity_m3_20261005/probe_contract.py`, `python3 .private/kity_m3_20261005/analyze_venues.py`. Private raw receipts remain local; public report/JSON preserve pins. The tiny feasibility calculations do not alter money admission.
