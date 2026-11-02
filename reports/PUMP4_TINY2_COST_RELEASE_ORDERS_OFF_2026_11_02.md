# PUMP4 TINY-2 — source-cost policy and actual-source OFF acceptance

2 November 2026. **COST_POLICY_OFF_PASS / ACTUAL_FLAT_SOURCE_REPLAY_PASS / FINANCIAL_GO_BLOCKED.**
Existing one-entry PUMP4 LIVE and Monthly v6 were preserved. No TINY-2 GO,
second writer, financial activation, lease acquisition on LIVE or broker mutation.

## Completed engineering result

The existing SeriesAccounting and serial supervisor now exercise an explicitly
pinned cost policy in ORDERS_OFF. Complete owned fills/fees, root account-wide
USDT history and paginated `/v5/position/closed-pnl` must reconcile. Every reported
closing quantity and each order's values/fees are checked; opposing discrepancies
cannot cancel. Unknown/missing/foreign/provisional evidence blocks the next entry.
Provisional rows may converge before certification; certified quantities cannot
be rewritten. History and certified envelopes survive restart and UNKNOWN gaps.

Observed accrued net uses the lower of known net and matched venue closed net,
minus observed arithmetic discrepancies and 0.000001 USDT reporting padding per
closing order. Missing positive credits cannot finance a new entry. A funding
debit already reserved is not charged twice when it later posts. A subsequent
negative source correction beyond a certified envelope permanently latches entry.
This is a proposed source contract, **not immutable future fee finality**. Padding
is a reporting tolerance, not a universal bound on exchange corrections.

Before reserving another child, its existing 1-USDT scenario risk must fit the
remaining day/week/drawdown/lifetime budgets. Scenario risk is not a guaranteed
loss bound. Duplicate plan/H1 is rejected before durable reservation. Existing
custody reconciles even when root sources fail. The default without this policy
still blocks a second entry. All OFF children retain the same lease and no_wire.

Two complete integrated model cycles ran through existing V1 owner/lifecycle:
entry → native stop → 40/60 exits → flat → restart → next distinct H1 → second
cycle → late first-cycle funding. Repeating either H1 never created another
reservation. Simulated exchange fills are explicit test-only operations outside
the OFF controller; these are **not two real trades**.

Source semantics: [Bybit closed-PnL API](https://bybit-exchange.github.io/docs/v5/position/close-pnl)
and [USDT P&L calculation](https://www.bybit.com/en/help-center/article/Profit-Loss-calculations-USDT-Contract),
checked 2 November. Actual nonempty records must qualify these semantics before
any financial use; empty pages do not prove a future trade's funding/fee coverage.

## Actual VPS acceptance and preserved LIVE

Immutable unselected candidate:
`/opt/bybot-research/pump4-serial-cost-off-20261102/candidate-db2eb8583301289d/app`.
Manifest `db2eb8583301289dc778983802b47f064a1959241935d84c58e393bc058c02fe`:
561 explicit files, including the complete pinned test-only Python dependencies.
No installed LIVE source was overwritten. The first package lacked a lazy pytest
dependency and failed before tests; its failure is retained, not counted as PASS.

**189 local / same189 VPS PASS**; VPS network namespace disabled and system tools
stubbed. The same tests in two environments are not378 independent broker checks.
One independent Astra/high review (actual runtime metadata verified) found1P1/2P2.
All three reproduced RED, primary fixes49 targeted PASS and final189/189 PASS.
No second independent signoff or financial approval is implied.

At **08:44:21.385 UTC**, accepted packet3aa49421 `--readback` independently reported
LIVE_ARMED_HEALTHY / LIVE_FLAT_WAITING_SIGNAL, source_age122ms, current H1 coverage
134 complete/3 unavailable/0 raw signals. No actual entry. Current scope/config
remain2de0b6ec/f715e676; new entries expire8Nov19:26:32.774UTC, custody persists.

At **08:48:55.100 UTC**, a separately manifested GET-only collector performed
11 real authenticated/public GETs with the existing bound credential loader,
same UID and key fingerprint. Original PID3669955 still held lock inode818853;
194 selected source hashes, wrapper, owner unit, DATA and Monthly unit hashes
matched before and after capture. Full series history since the selected scope's
start, positions/orders and closed-PnL were empty. No financial owner/controller,
lease, GO, journal or dispatcher was constructed by this capture.

Capture SHA `41b3596f4eabe11dc777edc1cffb97aa07eaacce3cbb14204d1370c5a555549d`.
A second network-denied process replayed those bytes through the OFF CLI at
**08:49:39.800 UTC**, preserving original source cutoff08:48:55.100; result
FLAT_SOURCE_REPLAY_PASS_NO_LIFECYCLE. This proves source/transport/file replay
compatibility on today's empty account. It does not prove real serial fills,
nonempty funding attribution, closed-cost finality or a physical owner handoff.
Full captures/balances remain private; public receipts contain hashes and status.

## Exact remaining conditions before a separate TINY-2 GO

1. Obtain the current V1 pilot's actual lifecycle and independently reconcile its
   entry, native protection, partial exits, restart, fees/funding and terminal state.
   It has not traded. No replayed historical signal, invented fill or automatic
   extension may replace this design gate. An expired no-trade pilot requires a
   separate explicit owner decision, not an assumed successful lifecycle.
2. Qualify this pinned closed-cost policy on **nonempty actual** exchange rows,
   including partial-close allocation and late posting/corrections. Monetary
   acceptance must explicitly acknowledge this source-envelope assumption and
   retain UNKNOWN blocking/correction latches. Current flat-source PASS cannot
   remove this condition.
3. Prepare the exact versioned serial financial scope and physical handoff packet
   against the then-current state: one original lock/one writer, custody/history/
   spent claims/epochs preserved, no overlapping scopes, rollback revokes entry
   without abandoning protection. Existing one-entry installer/GO is not a serial
   installer/GO. It was intentionally not applied, stopped or modified here.
4. Only then seek **separate exact owner GO**. Proposed50/30/20 allocation/gross/
   reserve,1 scenario,2 daily/3 weekly/6 drawdown/3 lifetime,≤10 sequential entries,
   one position and≤7-day entry period remain proposals, not active authority.
   A future packet must state exact dates and hold/cost-custody access horizon.

The source-cost policy is now **implemented and tested OFF**, superseding the
30Oct NOT_IMPLEMENTED blocker. Remaining real-lifecycle/source qualification and
financial handoff gates are not disguised as completed model acceptance.

## Monthly and next contract

At completion of this engineering cycle, today's14:30UTC/16:30Cyprus Monthly
execution window is still future. No BUY/CASH result is invented. Existing
`monthly-2` postwindow read-only check remains active; do not reactivate Monthly.
Its400/280/40 envelope and production selection/rules are unchanged.

The minimal Brain paired-decision contract is added to the existing
[diagnostic contract](../docs/TRADING_DIAGNOSTICS_CONTRACT_V1.md), documentation only.
Claude owns timely opportunity/advice research. No producer/judge/outcome/epoch,
Polymarket rule, research checkout or new strategy was run or changed here.

[Delivery](evidence/pump4_cost_release_20261102/delivery.json),
[actual GET audit](evidence/pump4_cost_release_20261102/actual-source-audit.json),
[independent file replay](evidence/pump4_cost_release_20261102/independent-file-replay.json),
[review](evidence/pump4_cost_release_20261102/review.json),
[source hashes](evidence/pump4_cost_release_20261102/verification-source-hashes.json).
