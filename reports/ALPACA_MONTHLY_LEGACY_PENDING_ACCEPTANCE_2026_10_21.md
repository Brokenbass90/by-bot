# Monthly: legacy pending-fee admission

**COST CLASSIFIER COMPONENT PASS / engineering candidate READY_FOR_OWNER_REVIEW.**
**Executable financial activation remains BLOCKED on the separate actual handoff,
final scope/config and owner actions below.** Base622d27a; no executable GO issued.
Source material527a9f0489bb11c3d9dcb88ab6ef6f7b2a2d704cb9b7b865699ea384f3788ea5.

## DONE

- Existing account-day fee producer now emits a replayable account admission
  context even before the first Monthly exit. Complete raw capture, pagination,
  tariff/calendar/assets, order ownership and terminal NET seal remain pinned.
  This reuses the existing source/book/allocation implementation and adds no ledger.
- Entire account pending-fee bound must fit the existing restricted reserve.
  Cash remains net of all posted obligations. Only Monthly-owned costs affect
  its strategy loss; NET stays OFF_PROTOCOL. API zero fee fields do not prove
  final posting. Unknown liability, foreign fill, source policy conflict, stale
  capture or missing legacy context blocks new entry.
- Already posted fees allocated to open Monthly positions are deducted once in
  aggregate loss admission. Closed-position fees remain in existing realized
  accounting. Missing legacy fees cannot falsely turn Monthly -7.99 into -8;
  a real Monthly open-position fee taking aggregate loss to -8 does stop BUY.
- Source context is cleared before each cost callback; restart rebuilds it from
  immutable evidence. Repeated import preserves original bytes/mtime. Late fee
  capture creates new evidence and leaves the prior estimate unchanged.
- LIVE owner scope and production config bind the same legacy seal, source
  cutoff, tariff, calendar and assets. Final pre-BUY validation replays the source;
  a valid owned-only estimate cannot bypass the owner's legacy policy.
- Actual restricted serializer/native manager path tested with an empty Monthly
  exit book: first BUY + full stop, accepted stop response lost, genuinely new
  binding instance recovers without another BUY/stop. All broker traffic is in memory.

## TESTED

| Acceptance | Result |
|---|---|
| Exact isolated local |241PASS,361.881s |
| Same exact isolated VPS |241PASS,252.853s |
| Package |53source files,17test files/helpers,40imports,0checkout fallback |
| Full synthetic paths |2receipts per exact run: production CLI frozen58 source/rotation + pending-fee replacement/finality |
| Independent review |One actualastra/high bounded component review;2P1 fixed with RED/GREEN regressions; same-worker4financial +8AST/first-entry targetedPASS, overlapping final suite |
| VPS GET/hash verification |Source/test/receipt hashes independently verified;93prior static pins unchanged, candidate UNSELECTED |

Initial VPS235case run had233PASS/2FAIL: a frozen fixture clock first obscured
an actual pending-source expiry before final BUY. Advancing that clock exposed
PENDING_FEE_STALE_SOURCE. Repeated AST dependency extraction consumed the5s budget.
A bounded LRU now caches only import-name extraction keyed exact source bytes;
file hashes, paths, dependency existence, source age and authority remain fresh.
Six drift regressions and an independent targeted check cover this optimization.
The initial FAIL is retained in evidence; it is not counted as final acceptance.

Source/test bytes checked before and after; sockets denied, VPS additionally uses
env-i/unshare--net/nice15. Real broker requests/writes0. Repeated environments and
review tests overlap; they are not482independent market observations.
[Exact manifests, receipts and reproduction](evidence/monthly_legacy_pending_20261021/README.md).

Review found posted open-position fees missing from the loss metric and an owned-
only estimate bypassing mandatory legacy context. Both are reproduced by named
regressions. Earlier84-targeted and later88-targeted checks are superseded by the
final exact package, not added to its241count. New source-policy cases are included.

Pending estimates are conservative admission evidence, **not terminal PnL or zero
commission proof**. Final posting still requires the original account-day finalizer.
All existing loss latch, WAL, recovery, custody, identity and unknown-state gates
remain. No source-model or frozen strategy change and no financial authority increase.

## REMAINING / OWNER PACKET

The reviewed financial software blocker is closed. No current defect in this
component is being deferred to the calendar. The private review dossier retains
confirmed400capital/280gross/40reserve/max4/loss8/no-new-borrowing preparation terms;
no repeat general intent question is needed. Higher capital is not approved.

Executable activation is still BLOCKED, precisely:

1. Actual original NET terminal identity/quantity/order truth and a complete
   terminal seal must exist before its costs can be classified. No personal exit
   was executed. The original exit envelope's single source-pin update remains a
   reviewed, unapplied proposal; the old wrapper is not advertised as ready.
2. Real legacy writer/scheduler retirement, single-manager ownership and safe
   rollback must be evidenced at cutover. Synthetic acceptance is not operational
   retirement. NET custody must not be dropped or silently adopted.
3. Final operational config and exact owner scope must include actual source/
   seal/input hashes and bounded terms. Those executable hashes remain unfrozen;
   no enabled Monthly service, selected pointer or financial grant was installed.
   Review/signing/cutover preparation is work before26Oct, not a reason to idle.
4. Actual30Oct completed selection source and2Nov fresh market/account/cash/reserve/
   ownership/native readiness are future facts. A valid CASH result is possible.
   Original2Nov14:30–14:35UTC (16:30–16:35Cyprus) window is conditional; no date carry.

Only items requiring actual future source/session facts are calendar-dependent.
A new real order still needs a precise valid owner packet. Existing NET/SHOP/HALT/
lock/profile/units/owner claims and all active risk settings were preserved; this
work does not provide a current NET protection readback.

## CLAUDE DELTA / NEXT MONEY GATE

Monthly legacy pending attribution: COMPONENT_PASS with complete first-entry and
mixed-day/restart/late-fee coverage. Technical candidate is reviewable; activation
BLOCKED on the exact future/handoff/owner inputs above. No research/KARTA/judge edits.

Next work is frozen PUMP4 V1 execution, without waiting for2Nov, Brain, InPlay or
trailing V2. Producer65/65 alone is not execution proof. KITY stays SPENT/ORDERS_OFF;
no retry or transfer of authority.26Octpacket/28OctPUMPexecutor/30Octsource checkpoints
remain; they are readiness deadlines, not promised trades or profit.
