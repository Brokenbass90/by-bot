# ATT1/ETS2S L2 lifecycle and L3 accounting contract

Date: 2026-09-06. Status: implementation specification for local research, not an implemented parity result or deployment authorization. Canonical checkpoint: `reports/CODEX_SESSION_CHECKPOINT_2026_09_06.md`.

## Decision

Build a small deterministic event reducer and an independent fixture oracle alongside the deployed L1 release. Reuse existing pure decision, quantity and reconciliation seams only where their semantics match. Start with synthetic execution events and no broker imports. Keep a future public-feed adapter separate from the reducer and never modify the running L1 shadow during burn-in.

Three options were considered: extend the money monolith (too much shared authority for this stage); adopt a full trading engine immediately (integration would delay P0); build a bounded pure reducer with an optional external comparator (selected). This choice accelerates falsification of fees, delayed entry and duplicate setups without replacing existing infrastructure.

Exact scope: linear USDT-settled ATT1/ETS2S research books. No cross-margin, inverse, options, liquidation or portfolio-profit claims. Every artifact has `money_authority=false`, `orders_allowed=false`, `private_api_allowed=false`, `promotion_authority=false`.

## Source facts and gaps

Verified from the canonical code on 2026-09-06:

| Contract | ATT1 | ETS2S |
|---|---|---|
| Signal | Frozen closed H1, short only | Frozen closed H1/H4/D1, short only |
| Entry metadata | Market, offset 0, wait 0 | Limit, offset 0.002, wait 6 bars |
| Stop | Native frozen wide stop | Raw stop distance multiplied by 4 exactly once |
| Targets | 1.20R / 2.50R; fractions .55/.45 | Native absolute target prices and fractions remain unchanged by the stop transform |
| Time stop | 336 hours | 336 hours |

Sources: `research_lab/att1_ets2s_signal_shadow_parity.py`, `strategies/elder_live.py`, `reports/ATT1_ETS2S_SIGNAL_SHADOW_PARITY_2026_09_04.md`.

Three implementation blockers must remain explicit:

1. The deployed L1 `observed_at_ms` is captured at cycle start. The checked 08:02 cycle completed at 08:08:23 UTC; max observed service duration was 385835 ms across the captured startup/scheduled invocations. L1 rows do not record per-symbol emission time. Backdating a simulated order to H1 close or cycle start would create an execution look-ahead error.
2. `_signal_payload()` in `scripts/run_att1_ets2s_signal_shadow.py` omits BE/trailing fields present in `TradeSignal`. ETS2S currently inherits BE trigger 1.0R and lock 0.1R, while its widened stop leaves native TPs unchanged. Do not guess whether BE means TP1 or 1R of the effective risk: serialize the explicit resolved signal fields and define the selected runner semantics in the new L2 profile.
3. The L1 files preserve `entry_wait_bars=6` but do not execute it or specify the wait clock. No local canonical execution consumer of that metadata was found. `entry_wait_bar_ms`, deadline inclusivity, offset anchor and fallback policy require a source-bound execution profile before ETS2S replay can receive a parity PASS. Do not silently treat six H1 bars as six M5 bars, or import old sealed outcomes as proof.

Until these profiles are bound, synthetic semantics tests are allowed, but `L2_PARITY=BLOCKED_PROFILE` for affected arms. ATT1 admission/reducer work can proceed independently. A new research proposal can select six H1 bars with limit at signal entry times 1.002 and cancel-at-deadline/no-market-fallback; it must carry a new profile ID and cannot be called unchanged replication without recovering the original execution specification.

## Identity, admission and position ownership

Inputs: strict JSON records with schema, source SHA, profile SHA, instrument-metadata SHA, stream, and timestamps. Reject duplicate JSON keys, bool-as-number, NaN/infinity, duplicate conflicting event IDs, unknown profiles and missing data. Use decimal strings for quantities/prices/cash.

`decision_id` binds `(sleeve, symbol, closed_bar_ms, L1 row hash, L2 profile hash)`. `order_id` is a deterministic research ID, never a real broker ID. `event_id` uniquely identifies one state transition; replaying identical bytes is a no-op, conflicting bytes are a hard incident.

One virtual position or pending entry per `(research book, sleeve, symbol)`. This is a research book, not a claim that the exchange supports independent simultaneous same-symbol sleeves. A separate portfolio arbitration fixture must prove one net money-symbol owner and shared slot/exposure rules before canary.

Admission requires timely `EXECUTION_FORWARD`, a validated non-null full signal, exact data/profile hashes, valid instrument sizing, no pending/open/reconciling position, and a fresh executable observation available after signal readiness. Bootstrap signals cannot be retrospectively admitted.

Same-bar duplicates are idempotent. Later signals while pending, partially filled, open or reconciling emit `IGNORED_POSITION_ACTIVE`, with opportunity-cost counters. They do not add quantity, replace geometry or create independent trade observations. Reentry after terminal exit requires a later bar and the selected profile's explicit cooldown; repeated observations of one setup are not separate statistical trials. No DCA or implicit opposite-side close/reverse.

## Time and causal execution

Required clocks: `bar_close_ms <= source_available_ms <= signal_ready_ms <= submit_ms <= exchange_event_ms <= received_ms`. Market-source event time and local receive time are both retained. Clock skew or missing ordering produces `NOT_CONFIRMED`; sorting late information into the past is forbidden.

The first simulated execution can use only a quote/trade event whose data was available at or after `submit_ms`. An OHLC diagnostic can enter no earlier than the next bar open strictly after the simulated readiness boundary. A candle that already started when the decision was ready cannot supply its earlier open. All such bar-only runs are marked `OHLC_PROXY`, not queue/fill parity.

Read-only L1 archive reconstruction may use complete historical causal input, but must be labelled historical replay. Existing L1 cycle-start timestamps cannot become a prospective executable timestamp after the fact. New L2 prospective observations need their own versioned writer and epoch after burn-in.

Market is an IOC-style simulated request, capable of zero, partial or full fills subject to a frozen slippage cap. Acknowledgement is not fill. A limit touch alone does not prove maker fill; public trade/depth evidence with a conservative queue model is required, and its assumptions are recorded. Missing depth means inconclusive fill economics rather than optimistic full fill. Bybit documents IOC market conversion, non-execution outside available liquidity, and explicit slippage tolerances. [Place Order](https://bybit-exchange.github.io/docs/v5/order/create-order)

## Reducer states and events

Represent entry-order status, held quantity/protection and exit-order status as orthogonal fields. The labels below describe views of that state, not an exclusive enum that could forbid a protective exit during entry. Accept protective exit fills whenever held quantity is positive; accept late entry fills until cancellation finality even if an exit is pending or partial. An exit does not implicitly cancel an outstanding entry.

| State | Accepted transition | Required invariant |
|---|---|---|
| FLAT | decision to REJECTED or ENTRY_PENDING | One accepted claim, frozen plan and entry deadline |
| ENTRY_PENDING | ACK / REJECT / EXPIRE / FILL | ACK changes no exposure; fills have unique execution IDs |
| ENTRY_PARTIAL | FILL / CANCEL_REMAINDER / PROTECTION_ACK / EXIT_FILL / RECONCILE | Every filled unit is exposure; no pretending a partial position is flat |
| OPEN | protection update / EXIT_FILL / time deadline | Remaining qty equals entry fills minus exit fills |
| EXIT_PARTIAL | next EXIT_FILL / late ENTRY_FILL / protection / RECONCILE | Unfilled exit remainder remains exposed and protected |
| RECONCILING | exact ledger/state agreement | Blocks new admission; unresolved state cannot become FLAT |
| TERMINAL | later eligible decision only | Zero position, zero pending entry/exit quantity, all cash flows reconciled |

Protection intent accompanies the first positive fill. The reducer cannot call a broker; `PROTECTION_ACK` fixtures separately establish protected quantity. Failed/unknown protection yields `INCIDENT_UNPROTECTED` and blocks entry progression, while an explicit simulated emergency exit can reduce the held quantity. Never discard actual exposure just because the existing final-fill adapter rejects it.

The existing `bot/live_native_fill_adapter.py` intentionally accepts only finalized fully filled entry orders. Reuse it for complete-fill oracle fixtures; it does not implement partial-fill lifecycle safety. New partial logic belongs in the isolated L2 reducer.

Every fill preserves stop constraints and checks actual risk after tick/quantity rounding. ATT1 may reuse `LiveNativeDecisionPlan` and target rebasing only under its exact frozen profile. That module currently registers ATT1/SBR1, not ETS2S. Do not disguise ETS2S as SBR1 or silently rebase its native absolute target prices.

For partial entry, provisional risk and protection cover the filled fraction immediately. Cancellation finality and late fills must be resolved before sealing final entry VWAP/quantity; `R0` is then fixed and never reset by TP1 or trailing. If a late fill violates the selected cap, record an incident and keep the extra exposure visible. No automatic clean-cohort inclusion.

SL, TP, BE, trailing and time-stop rules live in the immutable full execution profile. A stop cannot loosen after becoming effective. An update becomes effective only on its acknowledgement event; price observations used to derive a tighter stop cannot be replayed as earlier triggers. Time-stop deadline is first-entry-fill time plus profile hours; it does not reset on TP or delayed acknowledgement. In a bar-only diagnostic with ambiguous entry/SL/TP order, use a conservative stop-first envelope and flag ambiguity. For event replay use observed sequence; unresolved same-time ordering yields a sensitivity interval, not a fabricated sequence.

Intermediate TP quantities floor to qty step from the original accepted entry size. The final target requests the entire remaining executable quantity. Use exact Decimal quantities or integer step counts throughout planning and subtraction. The existing `bot.runner_state.plan_runner_target_close` is a comparison source only: its float remainder is not safe to reuse unchanged. Reproduced fixture: 0.3 initial qty, step 0.1 and fraction 0.55 yields first close 0.1 and float remainder 0.19999999999999998; the final call closes only 0.1 and leaves 0.09999999999999998. The new reducer must close 0.1 then exactly 0.2, ending at zero. Do not patch or deploy the money helper as part of this contract work. Position growth from another owner is contamination, not part of this strategy's clean result.

## L3 ledger

Per execution: ID, order/decision ID, side, qty, price, maker/taker classification, event/receive time, fee amount/currency, fee-source provenance and instrument version. A limit order is not automatically maker. Bybit supplies execution IDs, quantities/prices, fees, fee currency and `isMaker`, with multiple executions per order. Private records are a later redacted accounting-fixture input, never a capability of the public shadow. [Trade History](https://bybit-exchange.github.io/docs/v5/order/execution)

Use exact per-symbol tick size, quantity step, min qty/notional and effective timestamps. Do not raise a too-small quantity just to pass minimums. Current instrument metadata cannot prove historical filters. Missing historical metadata means `COST_OR_INSTRUMENT_PROXY`. [Instruments Info](https://bybit-exchange.github.io/docs/v5/market/instrument)

For a linear contract with direction `d` (+1 long, -1 short):

`gross_realized = sum(d * exit_qty * (exit_price - remaining_cost_basis_before_that_exit))`

`unrealized = d * remaining_qty * (valuation_mark - current_remaining_cost_basis)`

`net_realized = gross_realized - all_entry_and_exit_fees + settled_funding_cashflows`

`net_equity_change = net_realized + unrealized`

`R0 = finalized_entry_qty * abs(finalized_entry_VWAP - original_accepted_stop)`

For each entry fill, update the remaining weighted cost basis from the previously held quantity and that fill. Each exit realizes PnL against the basis immediately before the exit and leaves the surviving basis unchanged. Later entry fills cannot revise already realized PnL. Example: short 1 at 100, cover 1 at 90, then receive a late short fill 1 at 110: realized PnL stays +10 and remaining basis is 110. Aggregate finalized entry VWAP (105 here) is retained separately for the declared R0 convention; it is not applied retroactively to exits.

`net_R = net_realized / R0`; partial/open equity-R is reported separately. Keep planned risk, filled risk and fee-adjusted exposure separate. Fee amounts are positive expenses, rebates negative expenses. Slippage already embedded in fill prices is not subtracted again; its bps decomposition is explanatory only. While entry is partial, R0 is provisional and closed-trade net-R cannot be reported.

Funding cash flow uses actual signed position exposure and mark at each settlement: `-d * qty_at_settlement * mark * funding_rate` for the linear research model. Only settled funding is realized; projected funding is not profit. Missing mark/rate/settlement coverage blocks net-R. Intervals are symbol-specific and may change; do not assume every eight hours. Near settlement boundaries, model inclusion uncertainty and later reconcile to actual cash records; Bybit warns that activity within five seconds of settlement does not guarantee inclusion. [Funding Fee Calculation](https://www.bybit.com/en/help-center/article/Funding-fee-calculation/)

Public fee tables are scenario inputs, not actual account fee tier. Research runs declare base/stress assumptions and `ACTUAL_ACCOUNT_FEES_NOT_CONFIRMED`. A money gate requires exact current account fee evidence and observed per-execution fees. Funding/fees are separately deduplicated and survive restart; every cash identity must reconcile before terminal closure.

## Persistence and oracle gate

Append-only local event journal plus derived snapshot. Record the event before publishing the new state. On restart, verify the full chain, replay deterministically, compare the snapshot tip and reject conflicting IDs. A stale snapshot can be rebuilt from a valid journal; a truncated journal fails closed. No event overwrites an older receipt, no live process imports this package.

Independent oracle fixtures must not call the reducer's fill/accounting functions to calculate expected outcomes. Exact event identity, qty/cash conservation and all terminal states match; decimal tolerances are explicit only at exchange rounding boundaries. Passing shared helper tests alone is not independent L2/L3 parity.

Minimum adversarial matrix: duplicate decision; repeated next-bar signal while pending/open; stale signal; arrival after next-open; market zero-fill; partial-entry cancellation and late fill; unknown protection; TP1 partial; stop gap; BE activation after widened ETS2S stop; same-time ambiguous TP/SL; final-target dust; 336h time-stop; restart before/after receipt; conflicting execution ID; external position growth; positive/negative funding; fee rebate; fee currency mismatch; missing settlement; no double-counted slippage; same-symbol cross-sleeve arbitration.

## Exact build sequence and outcomes

1. Add `research_lab/att1_ets2s_lifecycle.py` and `tests/test_att1_ets2s_lifecycle.py`: typed IDs, strict execution profile, pure reducer, admission and duplicate/partial/restart fixture set. First tests use explicit synthetic profiles; default profile missing fields must fail. Outcome: one replayable lifecycle, zero external calls.
2. Add `research_lab/att1_ets2s_accounting.py` and its tests: decimal fill/funding cash ledger and qty/cash conservation. Outcome: independently hand-calculated net-R fixtures, including cost-killed and partial cases.
3. Bind full ATT1 profile and recover/source-bind ETS2S wait/BE/target semantics. Add explicit profile receipts. Outcome: no unresolved execution defaults; no borrowed sealed-economic verdict.
4. Add independent `tests/fixtures/att1_ets2s_lifecycle/` event/expected files and comparator CLI `scripts/verify_att1_ets2s_lifecycle.py`. Outcome: deterministic local L2/L3 contract receipt; separate bar-only proxy and event-level evidence.
5. Only after operational burn-in gate, package a new public zero-risk lifecycle version with decision-ready timestamps and full geometry, evaluate resource load, and obtain its own deployment/clean lifecycle receipts. The existing L1 evidence remains unchanged.

A local net-positive fixture proves arithmetic only. A new clean, costed, causal cohort with preregistered controls, concentration/fold checks, incident zeros and capacity evidence is required before a concrete micro-canary proposal. Its numeric economic gates must be frozen before examining new evaluation outcomes. The owner separately approves any money/risk change; no date or AI output promotes it.

## Independent design review

Strong-model review identified partial-entry protection transitions, interleaved-entry realized accounting, and float target dust. All three have explicit corrections above and exact adversarial fixtures. This is a reviewed design change, not a production helper fix or an L2/L3 PASS.
