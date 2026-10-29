# PUMP4 TINY-2: serial ORDERS_OFF gate — 29 October 2026

**MODEL_SERIAL_GATE_PASS / PRODUCTION_SERIAL_INTEGRATION_OPEN / NO_NEW_GO.**
This closes the previously specified two-cycle isolated gate; it is not a real
serial broker runner, actual fee finality, economic verdict or new money packet.

## Delivered and exercised

New `research_lab/pump4_serial_orders_off_v1.py` composes the UNCHANGED V1 owner,
lifecycle, AccountLease and hash-chained LifecycleJournal. It accepts only a fixed
FICTIONAL account fingerprint, `fixture_only=true` and ORDERS_OFF. Its V1 child
owners always use `apply=False`, no_wire and no owner GO; a planted GO is refused.
No keys loaded, no network implementation, no production constructor or VPS change.

Two full memory-exchange lifecycles execute sequentially through that path:
entry → verified fixture native protection →40% TP1 →60% TP2 →flat/costs pending →
explicit synthetic settlement/reserve →restart coordinator →next fresh plan.
One fictional exchange and account lease throughout;6unique model requests, no
position overlap. The reservation journal commits before a child's entry request;
crash/lost reply cannot release another slot or repeat a signal. Immutable older
claims/flows remain. A changed-price plan for the same signal is deduplicated by
symbol/side/signal-bar, not only plan hash. Cursor rewind rejected.

Aggregate model cash net carries across cycles; explicit pending-fee reserve0.05
per cycle is deducted ONCE (0.10total), never inferred from missing activities.
Loss/safety latches survive restart and day change. Source failure blocks new
entries while existing model custody continues. These are synthetic account/cost
assumptions; they establish no real upper bound on late fees, funding or gap loss.

## Verification

RED:10tests failed because the serial module did not exist. Initial GREEN exposed
an expiry-fixture history-window issue; test shortened only its permission period
instead of bypassing source completeness. Additional RED reproduced mixing a
source-safety block with a loss block; separate labels fixed that.

Final **89targeted tests PASS**, including16new serial cases and existing V1
owner/supervisor/execution-supervisor regressions. Covered duplicate/cap/expiry,
reserve-before-send, lost reply/restart, aggregate net without fee double count,
lifetime latch across a new UTC day, unknown source with retained custody,
forbidden GO, incomplete fee model and partial journal nonrepair.

CLI E2E: `.venv/bin/python -B scripts/rehearse_pump4_serial_orders_off_v1.py
--destination /private/tmp/<new-exclusive-directory>`.
Final r3receipt saved; repeat into the same directory was refused before any
fixture/evidence change (hashes AND mtimes identical). V1owner is byte-pinned in
CLI; all deployed-code equivalents/bridge files listed in delivery.json match
e4a0c15 byte-for-byte. No broad test rerun or VPS acceptance is claimed.
Independent gpt-6-astra/high static review completed (runtime context verified,
session01a188ef-4441-72f0-9bc4-1ed9dbb9eb92). Two Important defects reproduced
with4RED regressions and fixed: recheck expiry/latches between reserve and first
request; bind risk rows to current observation hash/time, propagate unknown-risk
inhibition and prohibit stale settlement. Reduce-only model custody is retained
when risk recording fails. Final89PASS. No second independent signoff claimed.
Review details in review.json; production/source/LIVE acceptance remains OPEN.

## Fresh existing PUMP4 check

21:17:29Cyprus /19:17:29UTC, existing activation.py **--readback** only, exact
packet66a7be9c. LIVE_ARMED_HEALTHY, reasonLIVE_FLAT_WAITING_SIGNAL,
actual_entry_executed=false, one_lifecycle_only=true, original lock818853,
PID3198429/0restarts, source_age135ms. No activation replay. Raw source remains
private; financial-control.json contains whitelisted facts and raw hash. The
readback's broker_writes counter is null, recorded UNKNOWN rather than zero.
Current one-shot expiry1Nov19:26:32.774UTC unchanged. Monthly untouched.

## Compact financial control

| Metric | Status |
|---|---|
| Project cash net after operating expenses | UNKNOWN: no complete period ledger |
| Project-wide verified realized trading net | UNKNOWN: accounts not reconciled together |
| Operating costs | PARTIAL: need actual period payments; recurring/one-off/accrual separate |
| Owner hours over7days | NOT_MEASURED, never inferred from chat/token count |
| Last fill / days since fill | No PUMPentry proven by fresh readback; full account history not captured |
| Portfolio gross/margin/stress | UNKNOWN in this scoped health readback; not assumed0 |
| Concentration | Measure cash risk/common loss drivers; no invented50%strategy rule |

There is no daily dashboard service or new reporting engine. Existing journals
and a sanitized dated JSON snapshot are reused; absence of cost inputs does not
turn the project profitable. Mark-to-market and fees/slippage are not counted twice.

## Exact next engineering gate

Implement the production-capable versioned serial owner/supervisor binding from
this fixture-only proof, retaining source/custody/send-once parity. It still needs:
- root-scope cumulative accounting with actual source-backed late fee/funding or
  independently justified pending reserve; model settlement cannot release LIVE;
- causal intake/cooldown/cursor mapping for the series, including all account
  history across slots, actual current quotes/lot minima/admission;
- one-writer physical handoff/rollback while preserving original lock, old spent
  claims, any owned custody and distinct exact GO;
- independent critical review and actual-source ORDERS_OFF acceptance, then a
  final bounded owner packet. Current10entries/7days/lifetime3USDT terms remain
  PROPOSALS, not activated. First V1 actual lifecycle is still unobserved; expiry
  without a signal is not execution/economic FAIL or an automatic extension.

No new strategy, Brain live filter, KITY money work, sealed outcomes or research
producer change. Model net is not a trading performance claim. The target for
2026 is repeatable permitted executions with evidence that net can cover costs;
profitability or a calendar date cannot be guaranteed by software development.
