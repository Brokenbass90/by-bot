# KITY_EXECUTION_MICRO_LIVE_V1 — local durable controller delivered

**Terminal money verdict: BLOCKED_EXECUTION. Local controller/replay delivered.**
This is implementation progress under the owner's preparation approval, not
real order/PAPER/LIVE readiness. No credential loader, HTTP writer, daemon,
service deployment, owner permit or monetary reservation was added.

## Exact owner bounds, now recorded

Owner reply to call_97d470124f1e40728c7172870f18ac54 fixes:

- aggregate gross≤210USDT;
- requested **hard final all-in loss≤15USDT**, including PnL/fees/funding/slippage;
- duration30min, followed by owned flat/readback;
- individual floor-rounding shortfall≤20.3%, disclosed in every leg's receipt;
- one experiment, no averaging/scaling/re-entry;
- exact subsequent money GO remains mandatory;
- purpose EXECUTION_MICRO_LIVE only; no KITY/C1–C3/edge/KEEP-KILL contribution.

`configs/research/kity_execution_micro_owner_bounds_20261015.json` is the
preparation contract; owner_money_go remains false. A short execution round trip
does not replace the research seven-day hold or change the canary rules.

## Implemented and verified

`research_lab/kity_execution_micro_runtime_v1.py` provides exact-bound plan
validation, the isolated SQLite FULL-synchronous hash-chained journal, action
proposals, conservative liquidation-value accounting and finality reconciliation.

- Intent is persisted before a possible send. Pending/unknown sends remain
  reconciliation work across restart; no duplicate entry/resend is proposed.
- Full original10-symbol/side identity and explicit per-leg rounding are sealed.
  Rehashing a plan with increased owner bounds does not make it admissible.
- Actual executions, not ACK/status, populate held quantity and fees. Duplicate
  execIDs under new envelopes do not double money; changed material identity,
  causal execution time or known fee conflicts block. Missing fee stays UNKNOWN;
  later fee enrichment changes costs once without repeating quantity.
- A partial/rejected entry stops remaining entries. Exit quantity is limited to
  proven owned fills, with reduceOnly and opposite side. Unknown dispatch of one
  leg does not prevent unwind of other fully reconciled owned legs. Known partial
  fills can request protection readback before entry terminal; no actual stop
  placement or stop-distance guarantee is claimed.
- Entry terminal with missing execution rows remains RECONCILE. Partial/unknown
  exits are never blindly resent. A terminal partial exit exposes its known
  residual for a new owned recovery intent; no account-wide flatten/adoption.
- Thirty minutes is anchored at first durable send intent (before possible
  exposure), not restarted from ACK/fill/reboot. Deadline observation is durably
  recorded and blocks later entries even after clock rollback. The controller
  proposes owned closing work; successful fills/flat at exactly30min cannot be
  guaranteed. Finality records actual flat/readback time and lateness.
- Liquidation accounting walks full bid/ask depth for the entire held quantity,
  uses actual entry/exit cash, actual fees, signed funding cash and an explicit
  source-provided funding reserve. Missing depth/fees/reserve produce UNKNOWN.
  Actual fill slippage is already in fill prices and is not charged a second
  time. The pure calculation explicitly does **not** authenticate/freshness-check
  source books; actual common-CTS/account/cost binding remains required.
- Finality requires own quantity0, all attempted orders terminal and their fills
  reconciled, complete owned broker flat/readback, known fees, funding coverage
  and exact sourced cash reconciliation. Merely being flat is insufficient.
  A final net loss below−15 is recorded as LOSS_BOUND_BREACHED, never a clean PASS.
- SQLite application identity prevents opening/initializing an unrelated DB.
  Plan/head/event-chain conflicts block recovery rather than deleting history.

`research_lab/kity_execution_micro_bybit_v1.py` maps actual Bybit-shaped
order/execution records to the journal without trading capability. It checks
symbol/side/linkID/brokerID/qty/orderType/reduceOnly/positionIdx, exact Trade
execution identity and fee currency. Missing orderLinkId requires an already
bound broker orderID; no symbol-only adoption. ACK is not a fill. Funding is not
misread as a Trade. Caller still must authenticate/pin the full account-scoped
GET response; canonical row hashes are not raw-wire authentication.

## Actual saved-source replay and current blockers

`scripts/run_kity_execution_micro_v1.py` defaults to no-send preview. It loads no
credentials, creates no journal by default and has no --apply/owner-GO activation
flag. Explicit --events plus --journal enables local offline replay only.
Exit2 is the deliberate readiness result, not a broker error/retry instruction.

Real saved intake replay:
`evidence/kity_micro_executor_20261015/saved_source_preview.json`.
Plan61aa1cb5a53508d5a6f785f27ed56ae9e3b54ae434c621708c8fdf1f034dddc7.
Original source/intake manifests remain byte-identical. Network-denied replay
returns the exact same JSON. No new broker observation was made in this cycle.

1. **Requested hard final loss bound is not established.** Current account is
   shared REGULAR_MARGIN. Native stop/IOC/unwind can request an exit, but Bybit
   documents that insufficient liquidity/slippage can leave an order cancelled
   or unexecuted. A trigger at15 is not proof that final net loss cannot exceed15.
   The code keeps hard_final_loss_cap_required=true and returns
   HARD_FINAL_LOSS_CAP_NOT_ENFORCEABLE_ON_PERPETUALS. Even a self-declared
   guaranteed_loss/owner_go field cannot override it. A policy-meaning question
   is pending; the requirement has **not** been softened.
2. The old measured minimum profile is210.266660 gross, above the owner's210
   cap. Its20.2716% LTC rounding now fits the explicitly allowed20.3%, but the
   gross excess does not. This is a saved-price result, not a current quote.
3. Real credential/account source custody, exclusive shared-writer ownership,
   broker transport, actual protection/recovery supervisor and fresh common2s
   account/instrument/book/cost binding are **not deployed or proven** by this
   local controller. Separate exact GO is still absent. No READY label or GO
   string is issued for an unexecutable/expired plan.

The loss requirement is a concrete policy blocker, not a reason to wait for
additional research outcomes. If it remains a guaranteed final maximum, keep
this perpetual experiment orders-OFF. If the owner explicitly chooses an
automatic exit threshold with execution-overshoot risk instead, record a new
versioned policy before completing real transport/binding and a fresh exact GO
dossier. No automatic policy edit, new order or launch follows from this report.

## Verification / preserved scope

**462 targeted PASS**:64 new runtime/Bybit-adapter/CLI cases,29 existing micro
geometry/clock cases and existing KITY assessor/CLI/signal-vector regression
coverage. Tests exercise a synthetic full10-entry/protection/readback/exit/
finality flow, partial/uncertain paths, restart and loss-breach cases. This is
not an actual broker lifecycle PASS. Full repository suite was not run.
Root review only; old independent-review quota restriction was not retried.

Alpaca code/installed packages/HALT/timers, Claude source/processes, ATT1,
liquidation collectors and frozen KITY research/C2/source receipts were untouched.
Today's Alpaca fresh preflight/exact GO/opening remains P0; no unattended wakeup,
PAPER cycle, broad architecture or research judge was added. No LIVE state was
re-queried or inferred fresh from this code delivery.

Official contract sources:
[Bybit order/IOC/partial-execution semantics](https://bybit-exchange.github.io/docs/v5/order/create-order),
[native stop lifecycle](https://bybit-exchange.github.io/docs/v5/position/trading-stop),
[account margin mode](https://bybit-exchange.github.io/docs/v5/account/account-info).
