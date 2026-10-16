# KITY exact-policy read-only watcher

> Native/root-only implementation; preserve exhausted reviewer restriction.

Goal: watch unspent9051ed…515155 until compatible capture or original expiry,
without financial authority, while Elder HEDGE_V1 engineering proceeds.

Approved spec: owner's latest KITY FRESH-ELIGIBILITY WATCHER request. Every120s
use existing pinned account/instrument/source/quantity/gross/rounding/compiler
and ten entry preflights. Policy scope, 70s,215,20.3%,50bps,15trigger,30min stay
unchanged. A compatible observation is notification only, never future-price
approval. Real personal GO still takes one separate new capture.

- [x] TDD pure lifecycle: pending/ready/expiry/claimed/staticdrift; one immutable
      terminal, one own lock, no attempt spent, post-capture expiry/claim guard.
- [x] Implement separate GET-only observer process; write only its own directory,
      preserve raw attempt sources; do not instantiate a sender/owner/journal.
- [x] Verify exact saved first/final captures offline and focused tests.
- [x] Install isolated read-only service; pin coreconfig/unit/policy and owncode;
      fresh account checks stay GET-only, oldwriter/source/wire state unchanged.
- [x] Native notification uses existing owner TG only after durable terminal;
      delivery claim before send, no blind retry. Separate chat heartbeat reads
      terminal/health, quiet unchanged, pause on terminal/original expiry.
- [x] Observe first actual attempt; publish sourced status and canonical pointer.
- [ ] Continue existing approved Elder plan Task3, HEDGE_V1 shadow only.
      Deferred by actual NET unprotected DAY-expiry incident; see checkpoint TOP.

Review: no cache replaces CTS; no real permit/selection/journal; queued personal
GO stops the watcher; after capture recheck expiry/claimed; static pins drift is
terminal, unknown market/account source is a dated blocked attempt; never
extend to another date or auto-repeat monetary experiments. Original9051 policy
and all spent predecessor artifacts remain immutable. No new strategy gates.

Actual closure: V1 lock-write denied by readonly sandbox; terminal preserved.
V1.1 pure pinned health observer fixed it. Native terminal13:05:56.306UTC:
READY206.694000,10+10checksPASS, oneTG15203, exitedsuccess. Readback16:04UTC;
60targetedPASS. AutomationPAUSED, no policyclaim/GO/order/thresholdchange.
