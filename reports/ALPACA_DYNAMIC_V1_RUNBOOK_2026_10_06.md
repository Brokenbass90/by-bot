# ALPACA_DYNAMIC_V1 — local orders-OFF runbook

October7 terminal update: read
`ALPACA_DYNAMIC_FIRST_WINDOW_AND_REARM_2026_10_07.md`/JSON first.
First window completed with one immutable XOM ranking, no executable reservation
or PAPER fill; current LIVE is flat/HALTED after confirmed emergency exits caused
by opening re-arm failure. Local isolation correction is tested, not deployed.
Do not restart the source job, extend its deadline, clear HALT, retire an expired
stop lifecycle as a stop fill, or backdate sizing. Exact emergency-exit/finality,
next permitted window, isolated PAPER lifecycle and separate LIVE GO remain.
The October6 armed/current-holdings statements below are historical snapshots.

October6 continuation: read `ALPACA_DYNAMIC_PAPER_INTAKE_2026_10_06.md`/JSON first.
Real PAPER adapter now exists but no broker PAPER order has run. The separate
source-only native job is armed throughOct7 13:35UTC; it captures closed data
and seals first ranking, no reservation/sizing/automatic send. Earlier local
command/input definitions below remain valid; their previous missing-adapter
statement is superseded. Actual manager/finality/unwind and LIVEGO gates remain.

Owner October6 prospective amendment supersedes the old monthly-reserve work
order. No November wait or invented Sep30 reserve. This entry point is offline;
it does not load broker credentials, submit orders or modify the LIVE manager.

## Frozen schedule and capacity

Read `ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json` and DELIVERY first. The initial
window is **October7 13:30–13:35 UTC /16:30–16:35 Cyprus**, using October6 closed
bars. Later ranking refresh is the first XNYS session of each ISO week; replacement
plans may use that sealed list at subsequent regular opens. No forced rotation.
The full broker calendar October2–November6 is pinned; calendar expiry blocks
further selection until a separately source-bound continuation is prepared.

There are three owned slot lineages: CRWD, AMD, META. Confirmed AMD terminal exit
creates one vacancy. Unused fourth-position capacity creates no replacement right.
One planned entry per session and one immutable intent per confirmed freed slot.
Unresolved reservations block additional slots; restart cannot reprice a plan.

Caps remain $487.42, gross0.70, maximum4, original per-slot notional/stop-risk
ceilings. Marked surviving exposure, reconciled cash less liabilities and modeled
fees may shrink quantity. Full native protection is part of every plan; fractional
quantity uses DAY. Broker acceptance, DAY expiry/re-arm and opening gaps must
still be proven by the existing protection machinery. A stop price is not a
guaranteed loss bound. No survivor rescaling or new stop/trail rule.

## Local command

From the canonical recovery checkout:

```bash
.venv/bin/python scripts/run_alpaca_dynamic_v1_orders_off.py
```

Before October7 open it returns `NOT_DUE` without creating a book or claiming a
first signal. The CLI uses wall clock and has no injected-time/send-orders flags.
Tests inject synthetic time through the Python function only.

For an actual causal rehearsal:

```bash
.venv/bin/python scripts/run_alpaca_dynamic_v1_orders_off.py \
  --input-bundle .private/alpaca_dynamic_v1_20261006/actual_closed_input.json \
  --output .private/alpaca_dynamic_v1_20261006/first_actual_receipt.json
```

The input above is a required future artifact, not an existing completed capture.
Output uses exclusive creation; preserve the first receipt. Default state is
isolated `.private/alpaca_dynamic_v1_20261006/rehearsal`. Input copies are hash-named;
rankings, owned slot lineages and intents are transactional SQLite records.

## Input contract

Exactly these top-level fields:

- `schema: ALPACA_DYNAMIC_INPUT_BUNDLE_V1`;
- `captured_ms`, `history_available_ms`: actual receive times, never future;
- `history`: all59 pinned existing-cache symbols, including SPY/QQQ; each row has
  `session`, `open`, `high`, `low`, `close`, ordered/unique/finite/positive;
- `snapshot`: account ID, actual `observed_ms`, source SHA256, explicitly verified
  single owner and cash finality, cash, unresolved-liability reserve and fee rate;
  positive position quantities/market values, open orders and exact linked terminal
  exit orders; `blocked_symbols`, per-symbol `quotes` and eligibility `gates`.

Exit rows bind `entry_order_id` to inherited/registered PAPER ownership. Each sell
has unique ID, same symbol, terminal status, positive filled quantity/price and
causal fill time. Aggregated quantity must exactly exhaust the owned lifecycle;
the symbol must be flat with no open orders. Partial/late/unlinked evidence cannot
release a slot. Confirmed exits persist a21-calendar-day reentry exclusion.

Quote fields: ask, receive time, qty step, minimum qty/notional, tradable and
fractionable booleans. Earnings, concentration, symbol eligibility and protection
gates must each be explicitly true. Snapshot/quote age bound is5minutes, inherited
from Alpaca's observation cadence; this does not touch ATT1's2s gate.

Every input needs capture provenance. **The offline module cannot authenticate
caller-provided account/gate booleans.** Synthetic fixtures never become actual
broker truth. A ranking pins raw history and selector dependencies, excludes
contemporaneously blocked/held symbols before the unchanged selector, and uses
only the immediately preceding completed session. Later runs reuse the sealed
weekly list; they do not search repeatedly for a buy.

## PAPER and promotion

`register_paper_fill` is synthetic lifecycle bookkeeping. It requires terminal
fill, full accepted stop quantity, correct account/symbol, no overfill and the
original plan's funding/gross/risk limits. It does not send a PAPER broker order.
An unprotected partial result blocks; recovery/unwind is not supplied by this
offline entry point. No cancellation/unreservation shortcut is implemented.

Before a LIVE GO dossier:

1. Preserve real October6 closed bars and first selection/quantity/reference-stop
   receipt in the fixed October7 window; archive gates and selected-account cash,
   fees/liabilities, calendar/universe lineage and contemporaneous quotes.
2. Bind that exact plan to the existing isolated PAPER entry/protection/recovery
   path; prove accepted full protection, partial-fill handling, terminal cash,
   late fill, restart and duplicate order reconciliation. Local simulations alone
   do not pass this actual-account gate.
3. Prepare exact one-owner handoff with existing LIVE manager/lock, immutable
   client ID, monthly-entry overlap exclusion, rollback and kill procedure.
   Freeze actual ticker/quantity, per-slot risk, gross/cash and fees before owner GO.
4. Only then request separate owner LIVE activation of this prospective version.

Current terminal state is **IMPLEMENTED_LOCAL_ORDERS_OFF**, actual promotion
**BLOCKED_DATA / FIRST_SELECTION_NOT_DUE**. No claim of improved net edge; new
forward version and unchanged monthly baseline can be compared prospectively.
Historical/untouched-holdout research is a separate improvement study, not a
mandatory November delay for this newly approved prospective version.

Stop here after the bounded Alpaca delivery. Next money task is KITY raw October7
23:55UTC → October8 independent basket parity/account feasibility. Preserve its
frozen research and money GO. ATT1's completed probes are not restarted.
