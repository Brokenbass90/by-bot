# L3 synthetic accounting core implementation plan

> Use superpowers:subagent-driven-development for this bounded pure slice.

**Goal:** Independently verify event-time cash accounting, explicit costs and
fixed initial risk before integrating the public L2 lifecycle.
**Spec:** `docs/superpowers/specs/2026-09-06-att1-ets2s-l2-l3-contract.md`.
**Architecture:** One pure immutable short linear-USDT ledger; stdlib Fraction
internally for exact rational cost basis, accepting bounded decimal strings.
No market/broker adapters, network, files, process calls or live imports. No
claim of real account fees, historical funding coverage or strategy net edge.

## Global constraints and exact decisions

- Create only `research_lab/att1_ets2s_accounting.py` and
  `tests/test_att1_ets2s_accounting.py`. All authority constants false.
- Public numeric inputs are finite decimal strings, bounded to 128 characters,
  64 coefficient digits and absolute exponent 64. No floats/bools. Use exact
  Fraction/integers, independent of ambient Decimal precision. Tests assert
  independently stated literal fractions/amounts, not implementation helpers.
- Explicit synthetic profile ID, original accepted stop, planned risk amount,
  currency USDT and provenance SHA are required. Only short linear books in
  this slice. Instrument/price-trigger/profile parity are separate gates.
- `AccountingPlan`, typed `Execution`, `FundingSettlement`, `EntryFinal`,
  `FundingSchedule`, frozen `AccountingResult`; expose
  `replay_accounting(plan, events, funding_schedule, *, mark_price=None)`.
  Caller must pass a FundingSchedule or explicit None; no optimistic default.
  API may use frozen per-event dataclasses, not unrestricted dict input.
- Each event has nonempty event_id, exchange_ms, received_ms; fills additionally
  unique execution_id, kind ENTRY/EXIT, positive qty/price, signed fee_amount
  (None means unknown), fee_currency and fee_source_sha256, liquidity MAKER/TAKER.
  Event timestamps are nonnegative ints, exchange<=received. Process given
  order, require nondecreasing exchange and receive clocks for unseen events.
  Identical event/payload or execution/payload is economically idempotent;
  conflicting IDs fail. For this synthetic API, full execution payload excluding
  event_id defines identity, as in L2; disclose delivery normalization as future
  adapter work. Old exact duplicates cannot rewind watermarks.
- Every entry updates held cost by adding qty*price. Every exit realizes
  qty*(held_cost/held_qty - exit_price), then reduces held cost proportionally.
  Exit qty cannot exceed held qty. Later entries never revise prior realized
  PnL. Track aggregate entry qty/notional separately from remaining cost basis.
- EntryFinal fixes R0 = aggregate entry qty * abs(entryVWAP - accepted stop).
  R0 never changes after that event, including partial exits. A late entry after
  finality remains visible in cash/quantity, marks sticky FINAL_ENTRY_DRIFT, and
  blocks net-R. Multiple distinct EntryFinal events fail; identical redelivery
  is a no-op. No-fill finality or zero R0 means no closed-trade net-R.
- Fees positive=expense, negative=rebate. Explicit unknown fee preserves qty
  and gross cash but blocks net totals and net-R; unknown is never zero. Reject
  non-USDT fee currency rather than silently applying a conversion. Preserve
  liquidity and source provenance; limit metadata cannot imply maker fees.
- FundingSettlement requires unique settlement ID, explicit mark>0, signed
  rate, supplied qty_at_settlement>=0 matching current held qty, source SHA,
  and settlement timestamp equal to exchange_ms. Funding cashflow for this
  short book is +qty*mark*rate. It is a settled event only; no projected cash.
- FundingSchedule explicitly lists unique sorted settlement times and a
  coverage window [start_ms,end_ms] with source SHA and complete boolean.
  Completeness is a synthetic fixture assertion, not proof of real coverage.
  Required settlements are the declared times from first ENTRY through latest
  ledger exchange time, inclusive; include zero-held observations when the
  schedule requires them. The window must cover that whole interval, and seen
  settlements must exactly match required timestamps; missing/extra coverage
  blocks net values/R (does not invent zero). None/incomplete schedule blocks.
  Empty expected schedule is valid only with explicit complete coverage.
- Result exposes exact held qty, remaining basis (None when flat), entry totals,
  gross realized, known fee total, settled funding, R0, issues and coverage
  status. Net realized = gross - fees + funding only if costs are complete.
  Unrealized (optional explicit positive mark) = held_qty*(remaining_basis-mark).
  Net equity adds it only when mark exists or held==0 and costs complete.
  Closed net-R requires entry final, flat, positive fixed R0, complete fees and
  funding, and no sticky incident. Open equity-R is not closed-trade net-R.
  Slippage exists only inside actual fill prices; there is no subtraction twice.

## Task 1 — implement with RED/GREEN and bounded review

At minimum independent fixtures:

1. Short1@100, stop110, entryfee.10, final, exit1@90 fee.09:
   gross10, fees.19, net9.81, R0=10, netR=981/1000.
2. Entry rebate-.02 and exitfee0: net10.02, netR=501/500.
3. Short1@100, exit1@90, late entry1@110 BEFORE final(stop120),
   exit1@100: first realized10 unchanged, late remaining basis110,
   final aggregate VWAP105, fixed R0=30, totalgross20, netR=2/3.
4. Short1@100, exit.5@90, entry1@110: realized5, held1.5,
   remaining basis320/3; exit1.5@100 => totalgross15.
5. Partial exits do not change finalized R0. Finality followed by unexpected
   entry retains qty/cash, freezes old R0 and blocks net-R with incident.
6. Short1, funding mark100 rate.001 => +.1; -.001 => -.1;
   settlement while flat with qty0 =>0. Wrong supplied qty rejects.
7. Missing fee, wrong fee currency, missing/extra funding settlement,
   incomplete/no schedule and insufficient window never fabricate net-R.
8. Gross-positive10 with fees11 => net-1; partial/open result has no closed R.
9. Identical events/executions/settlements idempotent; conflicts reject;
   unseen decreasing timestamps reject; replays and exposed state immutable.
10. Ambient Decimal precision1 does not affect exact outputs; invalid decimal,
    bool timestamp, nonfinite inputs and oversized numbers reject.
11. No-fill finalized sequence has no net-R; marked open short1@100, mark90
    has unrealized10, separated from realized0 and closed trade economics.

Run `.venv/bin/python -m pytest -q tests/test_att1_ets2s_accounting.py`.
Write report in `.superpowers/sdd/2026-09-07-l3-accounting-core/task-1-report.md`.
No commit by worker. Parent performs financial review, L2/L3 combined checks,
records precise scope and updates the canonical checkpoint.
