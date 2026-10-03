# ATT1 actual inputs — October 3 morning continuation

Status: `INPUT_COLLECTION_PROGRESS_ACTUAL_BUILD_BLOCKED`. NEW orders remain OFF.
Source HEAD at collection: `3fc65f8c10ad341edb3b8cdc1c0ecec25da29d04`.
Engineering Tasks 1–4 were delivered October 2; do not restart them.
Machine receipt: `ATT1_ACTUAL_INPUTS_PROGRESS_2026_10_03.json`.
Raw signed GET responses, source captures, Decimal checks and their manifest are
private in `.private/continuation_20261003/`; never stage raw account/API data.

## Measured progress

| Input | Evidence captured this morning | What it establishes |
|---|---|---|
| Broker identity / flat | Actual signed identity and complete account-wide USDT positions/orders at 05:17:18 UTC | Existing strict pure validators accept 0 positions / 0 orders. No synthetic identity or dedup in this acceptance |
| Effective OLD risk | Runtime heartbeat and deployed sizing source at 04:49 UTC | Base 1% × orchestrator 0.55 × allocator 0.8 = 0.44%, then ATT1 0.1, breaker 1 and volatility 1. Base env alone overstates the comparison ceiling |
| Account fees | Authenticated table, 923 derivative rows | All eight OLD symbols and 50 of frozen NEW 51 have taker 0.00055 / maker 0.0002. HFTUSDT is absent; do not guess its costs or change the universe |
| Recent cash | Eight executions joined to eight transaction rows by exact IDs, order, symbol, quantity and fees | Three recent OLD close receipts match broker cash exactly. Returned current UTC-day rows = 0 at capture; full OLD intent/cost finality is still unproven |
| Pause / process | Native pause true, OLD PID 492970 unchanged; broker flat | Pause remains applied. Do not repeat it, resume OLD entries or stop its management service |
| Public lifecycle | 04:45:46 UTC, same PID 1584802 / paired-observation epoch | Two IOC nonfills, six records, 0 filled simulations / 0 clean filled terminals / 0 held positions / 0 broker or order calls |

The broker cash identity is `change = cashFlow + funding - fee`; the transaction
field signs come from [Bybit's transaction-log specification](https://bybit-exchange.github.io/docs/v5/account/transaction-log).
This is a bounded reconciliation of published rows from September 27 through the
capture, not an edge audit or proof that later charges cannot be published.
The private numerical proposal remains `DRAFT_NOT_BUILDABLE`; no limits were installed.

## Remaining inputs and next engineering work

1. **Exact OLD handoff watermarks.** Full live log (508 rows), ATT1 trace (441 rows)
   and trade-events table (262 rows) do not provide all eight actual consumed-H1 /
   cooldown records. The deployed engine stores the required values in memory;
   its caller journal and coordinator tables are absent. Inventory an existing
   safe export seam first. If none exists, prepare a bounded local observation /
   handoff candidate at the existing boundary, with its restart/bootstrap limits
   explicit. Do not substitute trace wall time, anchors, zeros or a restarted
   engine for the old PID's state. No runtime change was made in this cycle.
2. **OLD intent / exit / cost closure.** Of 47 known submitted entry IDs, six lack
   same-ID close receipts. Bounded broker lookups returned six Filled entries;
   this does not establish their exits or final costs. Reconcile the six specific
   lifecycles from source-bound execution/cash evidence and record unavailable
   ranges explicitly. Flat GET is a current exposure fact, not historical closure.
3. **Position mode / pagination.** Global authenticated flat acceptance passed.
   Complete symbol-filtered chains contain duplicate symbol/index rows on six
   symbols; LINK returns indices 1, 2 and 0. The existing row gate rejects the
   duplicate chains. Its separate captured-row replay used a synthetic identity /
   empty-order wrapper and cannot certify account mode. Resolve endpoint cursor /
   mode semantics read-only before claiming ONE_WAY. Do not silently discard
   placeholder-like rows, switch broker mode or treat env `oneway` as broker proof.
4. **Funding reserve and minimum viability.** Frozen NEW time stop is 4032 × 5 min
   = 14 days. Captured OLD-eight funding intervals are 480 min; a constant-notional
   shock using the current negative limit for 43 settlements yields debit rates
   0.1419–0.43. This is an illustrative model, not expected funding, historical
   performance or a guaranteed future bound. Published limits and intervals may
   change. Source-bind a conservative reserve policy, then check stop risk + all
   cost reserves against existing daily cash and quantity/notional minima. Reject
   infeasible candidates; do not use only the latest rate, shorten the frozen
   time stop or increase risk to make a candidate fit.

Only after these inputs are complete can the existing orders-OFF builder produce
a refreshed actual-account packet. Its build acceptance is separate from money
permission. The unchanged 2–3 prospective filled clean terminals with terminal
net-R, fresh exclusive OLD comparison/handoff, reviewed selected-account
dispatch/protection/finality integration and separate owner GO remain required.
There is no installed NEW autonomous money runner and no one-flag activation.
Public observation continues while engineering closes specific missing inputs.

## Alpaca next operational gate

Broker snapshot 04:45:45 UTC / 07:45 Cyprus: same AMD/CRWD/META quantities and
ownership; floors 622.24 / 242.13 / 668.76, HWM 644.811 / 273.335 / 736.33 are
monotonic against the saved October 2 baseline. No filled sells were observed.
All three owned DAY stops expired after Friday close at approximately 20:05 UTC;
there are **0 open stop orders now**. Expired orders are not current broker
protection or continuous overnight/weekend coverage.

One NEW scheduled manager remains; OLD managers are absent and all 58 deployed
hashes match. Its latest receipt waits for the regular session. Broker next open:
**October 5, 13:30 UTC / 16:30 Cyprus**. Next re-arm is `NOT_DUE`, not PASS.
Use MASTER_HANDOFF section 4: let the existing manager run, then verify newly
accepted protection for exact remaining quantities, ownership and monotonic
floor/HWM. Inspect missing first-cycle protection by 13:35 UTC and escalate.
Do not repeat activation, run flat preflight or change stops over the weekend.

## Verification and scope

- Fresh broker-snapshot suite: `.venv/bin/python -m pytest -q tests/test_att1_broker_snapshot.py`
  → **30 PASS**. Exact Decimal joins, raw-body hashes, risk chain and source pins
  were independently checked by the private assessment script.
- One bounded `gpt-6-astra` / `high` evidence review: **PASS_WITH_SCOPE_LIMITS**;
  runtime model/effort verified. It reviewed the packet before the final global
  authenticated GET. That additional GET and resulting factual report update
  were verified by the primary only; no second review or implementation PASS claim.
- October 2's 242 local / 233 target tests and 14-session / 162-record receipt
  oracle retain their dates. They were not repeated and do not establish net edge.
- No broker writes, runtime code/config/DB/service/cron changes, orders, research
  evaluator reruns or sealed-window consumption. Foreign allowlist bytes preserved.
- Claude origin research ref remains `e965b68`; the latest visible KARTA health
  remains October 2, 17:29 UTC. No new PM2/TOLPA verdict asserted. NOCHNOY FX is
  KILLED / NOT_EXECUTABLE, Factory OFF; do not merge or duplicate Claude work.

Next bounded result: an exact source/export or local handoff-candidate receipt for
the missing OLD watermarks, plus closure or a precise data-gap receipt for the six
known lifecycles. Keep this input work separate from strategy or Factory expansion.
