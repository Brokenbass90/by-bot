# NET → Monthly: operational review packet, 22 October 2026

**CUTOVER_REVIEW_PREPARED; NOT AN EXECUTABLE GO.** This completes the procedural
part of the existing Monthly production-runner plan. The accepted financial
component remains `3374260`, material `527a9f0489bb11c3d9dcb88ab6ef6f7b2a2d704cb9b7b865699ea384f3788ea5`.
No financial software, strategy parameter, unit, pointer or owner grant changed.
The exact private review envelope is `.private/monthly_cutover_20261022/review-envelope.json`.

## Prepared now

- Rehashed all 53 accepted implementation sources and the actual four legacy
  unit fragments. The existing personal NET exit manifest still has exactly
  one stale source pin: `alpaca-oct15-owned-manager.service`. Its reviewed
  one-pin proposal matches the current fragment; all other manifest fields,
  entry identity, quantity, date, window and eight other pins are unchanged.
  The old owner launcher is **not ready to execute**; it still references the
  original manifest. Refreshing only the JSON without the launcher's exact
  manifest hash would not repair it. Neither artifact was replaced here.
- Current GET-only systemd capture confirms the NET manager timer remains
  enabled/active and SHOP remains disabled/inactive. A oneshot service being
  inactive between ticks does not mean its scheduler has been retired.
  This capture does not attest to current broker position/stop protection.
- Budget preparation terms: capital400, gross280, reserve40, maximum4 positions,
  single-entry ceiling168, no new borrowing. Frozen weights are not redistributed.
  Monthly realized net + owned unrealized ≤−8 durably blocks new BUY; custody
  continues. These are admission rules, not guaranteed maximum loss.
- The private envelope inventories all nine actual runner-config fields and
  separately tracks owner scope/GO, source closure and outstanding evidence.
  Its accepted package has53 files; the exact standing-authority closure has45.
  Extra rehearsal/diagnostic files must not be copied into the standing scope.
  Missing terminal/operational inputs stay null, never dummy valid hashes.
  The envelope has an explicit false-authority review schema; it is not a
  runnable production spec or a signed Monthly scope.

## Exact transition and stop conditions

| Step / actor | Action and required evidence | If not satisfied |
|---|---|---|
| 1. Codex, preparation | Present reviewed one-pin NET exit refresh **and** matching personal launcher hash, final retirement/config diff and rollback instructions. Owner approves these exact operations separately. | Preserve existing NET manager and protection; no launcher execution. |
| 2. Owner, original approved window only | Personally execute the corrected, source-pinned NET-only exit packet, unless original NET has already exited. Codex never executes or schedules it. | No Monthly entry; do not move the NET exit earlier or reuse an expired window. |
| 3. Codex, independent GET | Confirm original entry/exit ownership, full remaining quantity zero, terminal owned orders, no remaining NET orders/uncertain dispatch; retain executions, timestamps and raw activity pages. If already flat, prove that actual history instead of issuing another sale. | Partial/unknown exit remains with original manager/recovery. Do not stop its timer or send compensating orders. |
| 4. Codex, accounting | Build and independently verify the existing immutable `legacy_transition` seal from actual terminal truth. Bind it to source cutoff, tariff/calendar/assets, cash anchor, runner config and owner scope. Fully paginated activities and source-backed pending bounds include all account costs; NET costs stay outside Monthly PnL. | Missing/unclassified obligations block BUY. Broker-flat does not imply final fees; bounded pending fees are permitted only by the accepted policy, not treated as zero. |
| 5. Owner-approved operational cutover | After steps3–4, disable/stop only `alpaca-oct15-owned-manager.timer`; wait for its running oneshot/job to finish and verify it is inactive/dead. SHOP timer/service stay disabled/inactive. Do not kill a running recovery or remove locks/HALT/claims. | Any position, job/PID, unknown order or unresolved writer means keep custody and block Monthly. |
| 6. Codex, read-only retirement check | Use existing `capture_retirement`: four exact unit fragments/states, disabled timers, no jobs/PIDs/drop-ins/reload/transient state, exact read-only cron chain, no legacy writer process. Repeat under the original account lock at final BUY validation; capture≤2s, proof age≤5s. | NO_SEND; no relaxed freshness, fabricated retired state or second manager. |
| 7. Codex + owner | Finalize actual runner config, source/terminal/native-binding/profile hashes and original lock identity; derive `runner_config_sha256`, then separately hash the standing scope. Owner signs that precise scope. Keep the existing single `run_alpaca_monthly_cycle_v1.py` entrypoint; source/preview and financial dispatch remain distinct. | Budget approval or a review-envelope hash is not a signed executable scope. No enabled financial unit is installed by this packet. |
| 8. Existing runner, authorized entry window | Verify actual completed57+SPY selection, fresh broker/cash/reserve/liabilities/ownership and native readiness; reserve durable CID; independently recheck retirement and authority, then permitted entry/protection/reconcile. | CASH/NO_SEND are valid outcomes. Lost response uses same-CID reconciliation; no blind second BUY. |

The original personal NET exit and Monthly entry both have a five-minute
opening window. Completing the exit does **not** reserve extra time for Monthly.
If terminal proof, cost context, retirement or final authorization are incomplete
before the Monthly cutoff, that window is missed. Do not stretch it or carry its
selection to another day. This is an operational constraint, not a new gate.

## Rollback and custody

1. Before any order/uncertain dispatch: keep Monthly entries disabled. A verified
   empty, false-authority local release pointer may use existing
   `rollback_disabled`; it never switches an enabled financial service.
2. Any Monthly exposure, pending dispatch or pending accounting: **keep its
   sole owned manager and native custody**; block new entries. Do not roll back
   its journal, loss latch, floors/HWM, identity or account lock.
3. After NET retirement do not automatically re-enable its legacy writer,
   including when a Monthly deployment fails. No second owner may adopt NET or
   Monthly positions. A LIVE service rollback is a separately reviewed operation;
   the existing pointer helper does not implement it.
4. Revocation/expiry/loss latch stops new BUY, while valid owned maintenance
   continues. Neither renewal nor restart silently clears the durable latch.

## Remaining facts and authority, precisely

**Prepared private artifacts:** `net-exit-manifest.review.json`, matching
`owner-net-exit.review.sh.txt`, its exact diff, `retirement-commands.review.txt`
and the hashed review envelope. Shell syntax was checked; the owner launcher
was not executed. These review files are neither installed nor armed.
The actual executable runner config/scope remains unfinished until terminal and
operational inputs and a reviewed validity interval are bound. The field inventory
does not pretend to be a complete financial config. No software defect is
deferred to the calendar.

**Needs actual terminal evidence:** NET flat/order history, terminal seal and
cutoff/cash context. These cannot be forged in advance. Pending costs may be
admitted conservatively; final posting is never invented.

**Needs exact OWNER GO:** personal exit refresh/execution, retirement/selection
of financial units and standing Monthly authority/validity. None is implied by
this procedural review or by the already confirmed budget.

**Needs future source/session facts:** actual completed30Oct selection and fresh
2Nov window. Protection/exit and source evidence remain prerequisites, not a
promise of entry or returns. PUMP4 engineering proceeds without waiting for them.

Evidence: [packet verification](evidence/monthly_cutover_20261022/receipt.json).
The previous241 local/VPS financial tests are retained as component evidence;
they were not rerun or counted again for this documentation-only change.
