# PUMP4 V1: durable execution lifecycle, 22 October

**COMPONENT_PASS_TINY_BLOCKED.** Final code passed **91 tests locally and the
same91 on VPS** (70PUMP4 +21NET helper regressions), not182independent broker tests. Both used isolated exact code
with network denied; VPS also used`unshare --net`. All77 packaged files were
rehash-verified,33 imports had0checkout fallback. Candidate is UNSELECTED.
Material: `77e930dcc1d09833111da73cfc50aaaa33ecd39de46d6d3a252e7c3ed68ee70a`.

## Delivered code and integration

- `research_lab/pump4_execution_lifecycle_v1.py`: concrete Bybit-shaped
  entry/native-stop/reduce-only requests, immutable plan/quantity identity,
  exact40/60lot gate, cumulative fill/position reconciliation and static stop
  priority. One action is journalled/fsynced before handoff. Missing exchange
  response means reconcile-only, never another create. Terminal partial exits
  use a new CID for only the proven remainder. A fresh interpreter resumes the
  same quantities and action identities. Unrepresentable partial40/60blocks
  targets but does not suppress the valid168-hour full-position time exit.
- Reused `AccountLease`, `LifecycleJournal`, immutable `publish` and actual
  `SignedPostOnce`. Their KITY money policies/old GO were not reused. Account
  lease in this candidate is local; actual account-wide ownership is still a
  separate integration gate.
- `scripts/rehearse_pump4_cycle_v1.py`: actual CLI from one pinned, already
  accepted historical ZRO H1 prefix → existing closed-bar intake → frozen plan
  → durable lifecycle → signed requests against memory-only Bybit →40/60→flat
  and fixture cost reconciliation. Exact input prefix/hash and producer/plan
  match are checked. Reload after every order; separate regression tests use
  a new interpreter. No outcomes, judge, PnL or new prospective events computed.
- `scripts/rehearse_pump4_bybit_v1.py`: full/partial entry, partial TP1,
  entry/exit reply loss, uncertain pre-exchange send, stop race, missing native
  protection, time exit and unknown expenses. Unknown scenario names now reject
  before creating evidence, instead of silently executing normal.
- Append-only observations preserve seen fills even when protection is missing.
  Order identity/terminal status, executions and known funding cannot disappear
  or rewrite on restart. A never-verified current stop descriptor cannot
  self-authorize a supposed native exit.

One verified`gpt-6-astra/high`review plus targeted fix checks found and closed
the harness P2 and five lifecycle issues, including one P1. Regressions were
reproduced RED→GREEN. Reviewer checks overlap the final91; reviewer did not rerun
the CLI or VPS acceptance. Root performed those checks on the final exact bytes.

## Actual source/account checks

Seven authenticated GETs through the existing source-pinned read-only selected
account reader obtained fees, margin mode, wallet, complete positions/orders and
API metadata. No financial owner/controller was constructed. At the dated
snapshot the account was flat with no open orders; mode`REGULAR_MARGIN`.
Private balances/identity/raw captures were not committed or treated as a
PUMP4 allocation. Actual taker fees cover136of137frozen symbols; ZRO is
**0.00055/side (5.5bps)** versus6bps in the research model.

Fresh public instrument pagination/tickers cover136/137. **HFTUSDT is absent**;
it was not replaced or silently removed from the frozen universe. Source raw
hashes and collection times are retained. Current ZRO filters: qtyStep0.1,
minQty0.1, minNotional5USDT, tick0.0001, funding interval240minutes. At the
capture ask1.7731, conservative minimum exact40/60basket is3ZRO, gross5.3193USDT.
Constant-notional entry/exit fees would be about0.00585USDT. This is lot
feasibility, not approved sizing, actual slippage or guaranteed execution.

ZRO observed funding rate0.00005, current caps±0.005. For constant gross30USDT,
42four-hour periods imply0.063USDT at that observed rate, or6.30USDT at a current
adverse cap. These are scenarios: rates, limits and mark notional can change;
neither is a worst-case loss bound. Funding was omitted from the research model.

## Concrete remaining gates

1. Connect actual causal137-symbol H1/next-open source and authenticated,
   fully paginated account observations to this lifecycle. Its current
   observation schema is caller-supplied, not a broker-authentication proof.
2. Finish real tick/lot/margin/risk/funding admission. The module currently
   **rejects non-exact stop ticks**; it does not silently round the frozen stop.
   The historical CLI deliberately uses synthetic filters. For example its
   reference stop1.3146404800000007 is not on ZRO's current0.0001tick. Required
   execution quantization must be explicitly versioned before actual use.
3. Bind the single account-wide PUMP4 financial owner, durable send/recovery
   gateway and risk latches to the accepted sources and exact owner scope.
   Existing KITY/other writers must be reconciled before selection; no second
   financial owner was installed. The local request producer is not that gateway.
4. Present an exact TINY packet; only separately authorized real execution can
   establish actual native-stop acceptance, partial fills and execution costs.

A **proposal only** is saved: allocation ceiling50USDT, nominal stop risk1USDT,
gross ceiling30USDT,1position; stop-new-entry latches at day−2/week−3, review at
drawdown−6USDT; no new borrowing/leverage setting changes. Custody continues;
loss can exceed a trigger. None of these proposed values is financial authority,
and neither KITY300nor Monthly400approvals transfer to PUMP4.

Next engineering task is the actual-source/account adapter and admission above,
followed by its owner gateway acceptance. No calendar/Monthly/Brain wait.
This report does not claim a complete production executor or TINY readiness.

Evidence: [final receipt](evidence/pump4_bybit_rehearsal_20261022/receipt.json),
[local acceptance](evidence/pump4_bybit_rehearsal_20261022/local-acceptance.json),
[VPS acceptance](evidence/pump4_bybit_rehearsal_20261022/vps-acceptance.json),
[review](evidence/pump4_bybit_rehearsal_20261022/review.json),
[actual fees](evidence/pump4_bybit_rehearsal_20261022/actual-fees.json),
[public capacity](evidence/pump4_bybit_rehearsal_20261022/public-capacity-final.json),
[risk proposal](evidence/pump4_bybit_rehearsal_20261022/tiny-proposal.json).

Protocol interpretation follows official Bybit documentation:
[order creation](https://bybit-exchange.github.io/docs/v5/order/create-order)
and [native stops](https://bybit-exchange.github.io/docs/v5/position/trading-stop).
Market ACK is not a fill; market IOC can partially fill or cancel. Native Full
stop resizing is a documented mechanism, not real-account evidence from this
memory fixture. Accepted Monthly53source hashes, NET/SHOP/units/HALT and prior
KITY terminal authority remained unchanged.
