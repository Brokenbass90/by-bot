# PUMP4 existing-executor stream integration plan

> Execute natively with test-driven changes and one critical independent review.

**Goal:** replace full hourly candle downloads/repeated producer warmup in DATA only;
retain existing positive-signal financial HTTPS validation and owner authority.
**Spec:** owner's27Oct production137/ORDERS_OFF/sizing request; existing checkpoint.
**Architecture:** resident same frozen producer; existing hash-chain journal append
lock/durability; preboundary WebSocket subscription; raw confirmed close/new-open
custody. No change to frozen producer/intake files, risk, Monthly,60s or5s freshness.

- [x] Warm reducer: bootstrap exact frozen replay, original strategy call sequence,
  byte-identical state/decisions; locked unchanged-prefix check; clone-and-commit
  only after fsync; reject drift, gaps, duplicates withchanged clocks, environment.
- [x] Stream DATA supervisor: prearm savedprefix/epoch, raw beforedecode durable
  beforeappend, exactconfirmedclose/newopen separate, duplicate/conflict guards,
  preboundaryACK, originalwall/monotonicclocks; immutable observation output,
  no monetaryplan/authority. Existing financial TrustedSources performs its existing
  fullfreshHTTPS1002 check onlyforpositiveeligible signals.
- [x] Full137 resident CLI: metadata scope and explicitunavailable rows, chunked
  subscription ACKs, boundedT-120..T+90; no samehourreconnect/retry, preservefailures.
  Recovery beforefutureH1 via existing publiccapture/intake, CATCHUP notentry,
  unchanged epochs/cursors, disk/resource guards and graceful DATA-only shutdown.
- [x] TargetedRED/GREEN and existingexactproductionacceptance, criticalreview,
  exactVPSpackage/oneOFFownerhandoff withoriginal818853, noMonthly/prioritychange.
- [x] Actual137H1 source-to-durablepublications<=60s, recovery tests and financial
  sizingclassification. READY_FOR_MICRO_REVIEW onlyifallgates pass; nofinancialGO.

28Oct closure: exact406/406 and handoff24/24; seven real H1,945frozen decisions
match, first-hour protected healthPASS. SOURCE gate complete for observed cohort.
READY_FOR_MICRO_REVIEW remains conditional: executable LIVE-aware health/activation
packet and fresh eligible-signal financial admission are not claimed complete.
