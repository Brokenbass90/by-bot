# PUMP4 TINY-2: source accounting / isolated OFF integration

30Oct2026. **COMPONENT_PASS / SERIAL_GO_BLOCKED.** Current LIVE and Monthly unchanged.

Implemented root accounting across sequential children over existing authenticated
GET captures: raw/account/time/pagination checks, exact execution/order ownership,
terminal fill quantities, signed USDT fees and funding, bid/ask mark-to-market,
foreign activity kept visible. TRADE transaction fees are not charged twice.
Funding belongs to the unique actual holding interval; ambiguous boundaries stay
unknown. Complete pages/flat/no orders do not prove that later costs cannot arrive.

Append-only SeriesAccounting retains source IDs, late-cost revisions, UTC day/week,
drawdown and lifetime loss latch across children/restarts. History shrink and
rewritten execution identity reject the snapshot. Partial journals are not repaired.
Known partial net is not final net or a permit for another entry.

New isolated supervisor connects this to existing selected_owner, physical verifier,
TrustedSources, original AccountLease and unchanged V1 child lifecycle/owner. All
children share the carrier's lease/key and unconditional no_wire. Only source-pinned
ORDERS_OFF config is accepted; no dispatch option or financial GO writer exists.
Root source queries cover the full series, not only the latest child. Reservation
is durable before child reads/requests. Unknown root accounting blocks admission
and closure while existing child reconciliation continues.

Full integrated MEMORY-source cycle: entry -> native protection ->40/60 exits ->
flat -> restart -> BLOCKED_COST_RELEASE_POLICY_NOT_APPROVED. Simulated fills are
explicit test-exchange steps outside the OFF controller, not real broker orders.
The earlier two-cycle fixture-only proof remains separate evidence.

## Exact remaining gates

1. **COST_RELEASE_POLICY_NOT_IMPLEMENTED_NOT_APPROVED.** Root attribution and risk
   recording are implemented; releasing a real next entry is not. Reproduced flat+
   terminal+complete-pages case still has UNKNOWN unposted costs. Need an accepted
   source-completeness policy or independently justified bounded pending liabilities;
   do not turn empty logs, caller Booleans or current funding-cap stress into finality.
2. **ACTUAL_SOURCE_SERIAL_OFF_AND_PHYSICAL_HANDOFF_NOT_PERFORMED.** Candidate staged
   UNSELECTED. Existing LIVE owns the original lease. No switch, rollback execution
   or real-account serial acceptance is claimed. Future handoff must preserve lock,
   spent claims, source epochs and any custody; rollback cannot revive spent GO.
3. **FIRST_V1_ACTUAL_LIFECYCLE_UNOBSERVED.** Accepted design requires execution/cost
   evidence before serial GO, or a later explicit decision about an expired pilot
   without a signal. No invented cycle or automatic extension.

No executable personal command / READY_FOR_OWNER_GO. Proposed10entries/7days/
lifetime3USDT are not activated. This blocker concerns Bybit series cost release,
not Alpaca NET fees. Next: finish that policy/source proof and exact terminal cases,
then actual-source OFF/handoff review and a complete separate owner packet.

## Verification

**177 local / same177 VPS PASS**, including28 new cases. The same tests in two
settings are not354 independent broker checks. VPS tests used `unshare --net`.
No real private broker requests in tests. Default CLI returns ORDERS_OFF_NO_REQUESTS
without reading config or claiming a lease.

One independent gpt-6-astra/high review, actual runtime metadata verified:
01a18c3d-039a-7b93-9e75-848210221fb5. OneP1 reproduced in2RED regressions: rejected or
non-durable root risk view could still admit/close a child. Fixed by invalidating
that view; child reconcile retained. Initial independent suite21PASS; primary
checked final changes/177PASS. No second independent signoff or production approval.
Full E2E also found/fixed a normalized native-stop witness schema mismatch.

First VPS package17FAIL/160PASS: two lazy test dependencies missing, preserved in
[vps-packaging-failure.txt](evidence/pump4_serial_source_20261030/vps-packaging-failure.txt).
New immutable191-file candidate final177PASS; no test guard bypass.
Candidate: `/opt/bybot-research/pump4-serial-source-off-20261030/candidate-06cb58e310805b5b/app`.
Manifest SHA06cb58e310805b5babf951b83dace2545c9b0d2bef8b0d066aa40df738c2b5e7.
All existing selected-owner source closure bytes match HEAD, foreign allowlist
preserved untracked. No units/cron/HALT/locks/GO/risk/journal epochs changed.

[Delivery](evidence/pump4_serial_source_20261030/delivery.json),
[source hashes](evidence/pump4_serial_source_20261030/verification-source-hashes.json),
[local tests](evidence/pump4_serial_source_20261030/local-tests.txt),
[VPS tests](evidence/pump4_serial_source_20261030/vps-tests.txt).

## Existing money checks / continuation

30Oct09:57:10.012UTC (11:57Cyprus) existing packet66a7be9c **--readback**:
LIVE_ARMED_HEALTHY/flat waiting signal, actual_entry_executed=false,
PID3198429/0restarts, original lock818853, source_age268ms, same scope/config.
No activation replay. broker_writes=null is UNKNOWN, not numeric0. Raw private
receipt SHA9801551143812c642958f5a3dee05bbe895486fbac218ff0caa9747438597258.
10:08UTC GET: original four unit hashes unchanged, owner3198429/DATA3152955 unchanged.
Monthly timer active, service observed during scheduled dispatch, not a fresh
completed-cycle or selection receipt. Today close20UTC/source after20:20UTC still
future at that check; first conditional Monthly entry/CASH2Nov14:30UTC/16:30Cyprus.
Current PUMP entry expiry1Nov19:26:32.774UTC not extended.

Native Brain context/future join already delivered; Mac learning/Ollama strict
fact guards and native DATA transport remain next P1, not installed here. No new
research strategy, producer/judge/Claude code or LIVE Brain filter.
