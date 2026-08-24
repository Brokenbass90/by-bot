# XAU/MT5 demo tracker design

**Status:** design plus a tested pure paper-accounting core; no deployment, no
MT5 client, no order authority and no money decision. The core lives in
`bot/xau_mt5_zero_order_paper.py`; quote acquisition, frozen preregistration and
prospective demo tracking remain future gated slices.

## Objective

Create a zero-order, read-only research lane for XAU (and later explicitly
approved FX symbols) using the existing Bullwaves/MT5 demo data path. The lane
must measure whether a signal survives real quote timing, spread, session
boundaries, stops, take-profits, and gaps before any execution capability is
even considered.

This is deliberately separate from the semi-manual signal-copy execution
surface. A parser or AI proposal must never acquire the ability to call an MT5
trade method by being passed through this tracker.

## Current feasibility findings

The existing `scripts/forex_mt5_demo_bridge.py` can discover signals and has a
dry-run launcher, but it does not yet provide a complete zero-order quote,
virtual-position, outcome, or random-control journal. The `signal_copy/` path
has a more complete parser and account/quote context, but its journal is for
actual MT5 positions and its pipeline is not a paper outcome engine. There are
also import-time tests that require `SIGCOPY_MT5_TOKEN`; that testability gap
must be fixed without printing or persisting the token.

The first XAU hypothesis worth an exact replay is **session breakout/retest**:

* historical diagnostic: `+3.915R` base;
* historical diagnostic: `+3.012R` stress;
* sample: `N=13`;
* preflight: `false`.

This is an interesting hypothesis only. The sample and failed preflight block
money authority. Other examined round-sweep/trend-pullback variants were not a
promotion candidate; the older best round-sweep result was `-2.832R` with
`PF=0.888`. Structure-break evidence was concentrated and also failed
preflight.

## Hard safety boundary

The tracker must have no reachable `trade_*` path. Its process identity,
credentials, and configuration are read-only. The first deployment after MT5
token rotation must verify the exact demo account identity, server/broker
identity, symbol contract, and account mode, then write that identity into the
receipt. A token is an input to an authenticated read-only client only; it is
never written to a journal, report, exception, environment dump, or Telegram
message.

The following are prohibited in this lane:

* `order_send`, `trade_*`, position modification, or close calls;
* automatic promotion of a signal, model output, or backtest;
* live-account discovery by fallback credentials;
* use of a stale quote as if it were an executable fill;
* changing a strategy, universe, or cost rule after the first preregistered
  decision.

## Components and contracts

### `SignalEvent`

An immutable, causal signal record:

* `signal_id`, strategy/version, symbol, side, event UTC;
* source candle/feature boundary and data-source hash;
* entry/stop/take-profit geometry and intended validity window;
* regime label and feature snapshot hash;
* preregistration hash and evidence-universe role.

It must be possible to reconstruct why the signal existed without querying a
future candle.

### `QuoteSnapshot`

The quote observed by the paper adapter at the decision time:

* UTC timestamp, bid, ask, midpoint, spread, tick/contract metadata;
* source response hash and freshness age;
* market/session state and an explicit `quote_valid` decision.

The adapter must use side-correct prices: a long entry is evaluated at ask and
a long exit at bid; the inverse applies to shorts.

### `PaperPosition`

An in-memory/state-journal representation with no broker position:

* entry quote and effective fill price after the preregistered spread/slippage
  rule;
* quantity, side, stop, take-profit, signal and decision IDs;
* current protection state and last valuation timestamp;
* lifecycle state (`pending`, `open`, `closed`, `invalid`, `expired`).

No position may be marked open without a valid quote and a recorded paper fill.

### `PaperOutcome`

An immutable close record containing:

* exit timestamp, side-correct exit quote and effective fill;
* close reason (`stop`, `take_profit`, `time_exit`, `gap`, `invalid_data`);
* gross/net PnL and R after the fixed cost contract;
* MAE, MFE, holding time, gap amount, and quote freshness;
* data-quality status and source hashes.

If the first tradable quote is already beyond a stop, the outcome must record a
gap/open event rather than pretending that the stop filled at its requested
price.

### `ControlAssignment`

For every preregistered strategy decision, write a deterministic zero-order
control assignment before observing the outcome. The control uses the same
symbol universe, timestamp window, regime gate, cost model, holding horizon,
and quote-validity rules. Its side or entry time is derived from a recorded
precommit hash; it must not be chosen after seeing the strategy outcome.

The strategy and control are separate event streams. They may share market
quotes, but a control event must never mutate a strategy position or consume a
broker slot.

## Journal and idempotency

Use an append-only journal (JSONL or SQLite with immutable event rows) with a
schema version and hash chain. Each row includes `event_id`, `parent_hash`,
`prereg_hash`, `source_hash`, `created_at_utc`, and an idempotency key. A retry
must produce either the same event or an explicit retry/error event; it must
not duplicate a fill or outcome.

At minimum, retain separate streams for:

1. raw read-only MT5 responses and data-quality errors;
2. signal decisions;
3. paper fills/positions/outcomes;
4. control assignments/outcomes; and
5. health and deployment receipts.

Private tokens and full environment values are never journaled. Public source
and configuration hashes are sufficient for replay identity.

## Processing sequence

```text
read-only MT5 quote/account snapshot
        -> validate identity, session, freshness, and symbol contract
        -> append SignalEvent (or explicit no-signal/error)
        -> append deterministic ControlAssignment
        -> paper fill at side-correct quote + fixed costs
        -> update PaperPosition from subsequent causal quotes
        -> close on stop/TP/time/gap/data invalidation
        -> append PaperOutcome and health receipt
```

The process should continue per symbol after an individual public-data error,
recording the error and retry state rather than converting a partial cycle into
a false “no signal” result.

## Required tests and gates

### Unit and contract tests

* long and short bid/ask fill direction;
* stale, crossed, missing, and out-of-session quotes fail closed;
* stop-first versus take-profit-first ordering when one bar touches both;
* gap-open exit accounting;
* fractional quantity and XAU contract-size/point-value calculation;
* UTC session and daylight-saving boundary handling;
* deterministic control assignment stability, collision handling, and
  precommit hash verification;
* append-only hash-chain validation and idempotent retries;
* proof by static test that no `trade_*` or order-send method is imported or
  called by the tracker;
* token-free logs and receipts;
* exact demo identity captured in a deployment receipt.

### Research gates

1. **Data gate:** sufficient contiguous XAU quote/candle coverage and a frozen
   symbol/session manifest.
2. **Causal replay gate:** signal, quote, fill, stop, TP, and gap rules match
   the deployed paper adapter without future leakage.
3. **Control gate:** every eligible decision has a paired control assignment;
   no silent omissions or post-outcome sampling.
4. **Evidence gate:** preregistered trade-count, holdout, cost-stress,
   concentration, and top-outlier removal checks pass.
5. **Paper gate:** prospective zero-order paper events are healthy for a full
   review window, with no data, identity, journal, or safety incidents.
6. **Promotion gate:** only an explicitly approved owner decision can create a
   separate execution project. This tracker itself never gains money
   authority.

## Initial implementation slice

The first implementation should be a small pure paper adapter and journal,
not a general-purpose MT5 executor:

1. freeze XAU symbol/session/cost configuration and preregistration;
2. add read-only quote acquisition with per-symbol failure isolation;
3. implement the five records above and append-only receipts;
4. replay the session-breakout/retest hypothesis with its original `N=13`
   diagnostic, then extend only through predeclared rules;
5. start prospective paper and paired control collection;
6. review the data-quality and evidence gates before considering any next
   strategy or account.

Until these gates pass, XAU/Forex remains research/paper only. The historical
`+3.915R` result is not an expected return, a broker promise, or a reason to
fund the demo account.
