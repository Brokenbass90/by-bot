# Gold macro: reuse Claude sources, resolve data contract — 29 October 2026

Decision: reuse existing research; DATA_QA_PARTIAL, ECONOMIC_VERDICT_NOT_RUN.
Published research ref30951f9abcdcf56ae4bf853d9168d2ac2d24a34e verified against
origin today. No new gold macro prereg or gold macro economic verdict found in
that ref. Existing17Oct macro preregs are BTC, not an automatic gold mandate.

## Verified dataset facts

| Source | Rows | Basic structural checks |
|---|---:|---|
| Local zoloto_h1/XAUUSD.npz |45684|No duplicate/nonincreasing times, nonfinite OHLCV, invalid high/low geometry, or off-grid timestamps|
| Published/local gold_m5/XAUUSD.npz |87439|Same checks pass; exact published Git blob match|

H1 SHA6751d617e4836b8198c90bb95dbf06736e5066a76b6cc3dc08bb3e27901aec45.
It exactly matches the intermediate mt5_h1_new file (timestamps and OHLCV).
H1 is local data, not found as a tracked zoloto_h1 blob; its bytes are pinned here.
Calendar v2 SHAcee6e62d73d2b1a34ca75b3bde6f9c3c3b9ec671f5ead0484519840ee931ee11
matches the published manifest. Gap counts include normal closures and are NOT a
missing-session verdict. No trading returns or sealed outcomes calculated.

## Material corrections before any economic run

1. **Source/time conflict.** 26Oct feasibility says FxPro/UTC; 30Sep delivery says
   MetaQuotes-Demo; published DEFEKT_VREMYA_MT5 and mehanizmy.mt5_v_utc say H1
   labels are server EET/EEST. Existing gold_glub_utc loader converts them. Reused
   only that pinned conversion in memory, not a new offset/model. Corrected range
   2018-01-02T07:00Z through2025-09-29T20:00Z; no duplicate/reversed times.
   Research must identify one raw→UTC lineage and never convert twice. M5 clock
   provenance still needs its own proof; do not assume H1 source or offset.
2. **Calendar count is not eligible sample size.** Calendar CPI63/NFP62/FOMC32
   includes dates through2026, while prices endSep2025. Using the published H1
   conversion, event-containing bar plus next-hour opening exists for CPI51,
   NFP49,FOMC22. These are bar-presence counts only: warmup, full hold, eligibility,
   simultaneous releases and independent event clustering can reduce them further.
   M5 provisional UTC joins:15/14/10; not accepted until its timezone is proven.
3. **First-hour reaction must be defined.** CPI/NFP08:30 America/New_York falls
   inside an H1 bar containing30minutes before release. Its full open→close return
   is not a pure first60minutes post-release. Freeze a precisely observable rule
   before looking at returns; exact first60minutes requires suitably aligned finer
   bars. Neither H1 nor M5 OHLC proves exact intrabar stop execution when order is
   ambiguous. No choice of the best entry/hold/filter after seeing results.
4. **Costs are venue-specific.** Existing atlas_izderzhek.py summarizes hourly
   spreads, not event-minute bid/ask or realized slippage. It can add symbols and
   writes its atlas: NOT executed. Current demo preflight/calculators prove MT5
   mechanics, not Bullwaves quotes, news costs, fills or strategy profitability.

## Narrow division of work

Claude owns one explicit gold macro prereg and economic calculation on accepted
source/window, with independent matched controls, all-in cost stress, uncertainty,
concentration/regime checks and full usable-sample/exclusion disclosure. Existing
BTC preregs/results cannot be silently reused as gold validation. A consensus
surprise mechanism is still BLOCKED_DATA; first-bar reaction is a different test.

Codex owns source hashes/time/coverage and execution feasibility. Reuse existing
MT5 get_chart_ticks_history or bounded bid/ask sampling after exact source-clock,
release schedule and capture contract are specified. Capture request-start/receive
UTC, source/server time, symbol, bid/ask, gaps and raw response hashes; measure the
actual target venue, mark demo separately. Quotes cannot prove realized slippage;
only stress estimates until actual permitted executions exist. No new collector,
schedule, broker mutation, terminal change or strategy run was installed here.

Gold macro events offer a few scheduled dates/month, not daily trades or proven
income. Existing Monthly/PUMP4 scopes/expiry unchanged, KITY engineering staysHOLD.
Polymarket numbers in the pasted PM note were not independently checked by this
scoped gold intake. No Claude message sent; published handoff is available.

Evidence: reports/evidence/gold_macro_intake_20261029/{qa,source_hashes}.json.
