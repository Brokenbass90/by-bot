# ALPACA_DYNAMIC_V1 — local orders-OFF runbook

October7 closure: read `ALPACA_INCIDENT_CLOSURE_AND_PAPER_2026_10_07.md`/JSON first.
Isolation fix is installed, exact emergency exits reconciled, broker flat and
entry HALT retained. PAPER upkeep is staged; actual PAPER remains BLOCKED_DATA.
The earlier not-deployed/first-window statements below retain their timestamps.

## October8 actual PAPER continuation

Next selection window is **13:30–13:35 UTC /16:30–16:35 Cyprus**. Do not rerun the
Oct7 source-only collector, extend its deadline or modify its sealed SQLite.
The new app is `/opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/app`;
source-bound copied book is its sibling `runtime/rehearsal/replacement.sqlite`.
Manifest23 SHA is `4f6e5288790174b9a9fdfb031d4e7a229c8b852ed2eef96785003d30961f76d3`.
The copy starts from the exact Oct7 source SHA `f34d90c8669dc1f1b61710852d47381c23c0f98dbeff8333b540ccb5e76919f7`.
Verify these pins/lineage and the copied existing ranking, do not initialize a
fresh book or regenerate a winning list.

Prepare a real `ALPACA_DYNAMIC_INPUT_BUNDLE_V1` in that window: prior sealed
closed history, fresh authenticated selected-LIVE account/quote/asset/minimum,
linked actual terminal exits, fees/unresolved-liability reserve, earnings and
concentration, scoped protection and exclusive owner evidence. Preserve raw
sources with receive times/hashes before asserting any gate. No guessed
`cash_finality_verified`, `single_owner_verified` or fee rate. PAPER's large
cash balance does not enlarge the intended LIVE slot/capital/risk budget.
Use the real inherited slots and frozen deterministic ordering; with all three
now flat, the allocator may select CRWD lineage before AMD. Never force a slot.
If any source/gate is unknown, preserve BLOCKED_DATA without a reservation.

Commands below are on VPS; `actual_input_oct8.json` and `plan_oct8.json` are
required **future real artifacts**, not existing fabricated plans:

```bash
cd /opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/app
/root/by-bot/.venv/bin/python scripts/run_alpaca_dynamic_v1_orders_off.py \
  --runtime /opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/runtime/rehearsal \
  --input-bundle /opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/runtime/actual_input_oct8.json \
  --output /opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/runtime/plan_oct8.json
```

Before broker PAPER dispatch, freshly verify exact PAPER account
`4cdbfb77-d1e0-4789-86b2-341bc886efaf`, XOM flat/no orders/no competing owner,
all active writer sources/cron, shared original account lock and legacy XOM
exclusion. The exclusion was prepared under lock with no position/order change;
its exact SHA is `8171cd5ef14f8374e75f6406476d254c816465ef96cab8a52ac335d2f2122e3f`.
Do not remove it while any owned position/order/finality is unresolved. All five
legacy positions and old exclusion keys are outside this candidate's write scope.
Any conflicting writer or source drift blocks dispatch. No second owner or cron
is installed by this delivery; maintenance is an explicit bounded operator call.

After the plan is durably `RESERVED_ORDERS_OFF`, default rehearsal is GET-only:

```bash
/root/by-bot/.venv/bin/python scripts/run_alpaca_dynamic_paper.py \
  --plan /opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/runtime/plan_oct8.json \
  --plan-store /opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/runtime/rehearsal/replacement.sqlite \
  --paper-env /root/by-bot/configs/alpaca_paper_local.env \
  --paper-account 4cdbfb77-d1e0-4789-86b2-341bc886efaf \
  --runtime /opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/runtime/broker_paper \
  --output /opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/runtime/paper_read_only_oct8.json
```

Only within the actual permitted window and after all gates pass, repeat this
exact command with `--paper-submit` and a **new unique output path**. This is
PAPER authority already approved by the owner, never a LIVE activation command.
Keep exact plan/reference price/quantity; an unfilled limit is not repriced.
Persisted uncertain dispatch is GET-recovered by CID, never resent or cleared.

Once initial receipt is `PAPER_PROTECTED`, use the same plan/store/profile/
account/runtime arguments with `--paper-maintain`. Default reads only; adding
`--paper-submit` permits upkeep of that exact owned PAPER lifecycle. It cannot
open another entry. For proof-scoped operator emergency only, also add
`--paper-unwind`; never DELETE account positions or invoke an unrelated legacy
kill wrapper. Every output path is exclusive-create and must be unique.

At initial fill, archive full STOP acceptance/readback and exact position size.
Restart by invoking maintenance with those same sources/state, proving no second
entry or stop. If held overnight, verify expired DAY and next regular-session
re-arm **October9 13:30 UTC**, unchanged floor/full remaining owned quantity.
If stop fills first, reconcile its actual terminal instead; that does not prove
DAY re-arm. Partial fills, 422, lost responses and duplicates are covered locally
but actual observations must retain their real type, not a manufactured fault.

A scoped unwind may partially fill or remain pending: retain state/uncertain
CID and continue GET reconciliation; do not resend missing/unproven commands.
Stop fill during cancellation is a STOP exit; mixed native/market fills retain
both. Gross before fees is not net. Read authenticated fills/account activities,
resolve costs/liabilities/coverage and preserve a terminal receipt; the upkeep
module deliberately returns `*_PENDING_FINALITY` until external finality is proven.

Return one actual `PAPER_EXECUTION_PASS / BLOCKED_EXECUTION / BLOCKED_DATA` only
from those sourced results. Initial `PAPER_PROTECTED`, synthetic tests, staged
source or an empty broker account alone do not meet the end-to-end gate.
Then prepare exact LIVE ticker/qty/caps/stop, sole ownership/monthly-overlap,
emergency and rollback dossier. **No HALT clear/new LIVE entry without owner GO.**

## Installed incident rollback boundary

The old LIVE wrapper is retained at
`/opt/bybot-research/alpaca-rearm-isolation-20261007-r2/original_run.sh`, SHA
`fdd74d2834e2a3010f45d33cf984f21e0239493a361c689d712071f34396e24a`.
Installed wrapper SHA is
`dc5a9c0f7b8e934ecbc783c85284cea56f0a4c8c4dbc8b5093ed912590726391`.
A code-only rollback is permitted only while freshly globally flat/no orders and
HALT true, under existing runner/account locks: archive current wrapper, verify
old wrapper/package pins, atomically restore wrapper bytes, fsync and run its
GET-only readback. Do not roll back the reconciled ledger or delete the incident
archive; that would resurrect closed ownership. Never treat rollback as LIVE GO.
The earlier draft staging app was never selected; do not overwrite sealed apps.

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
