# Event Universe V2 — source-finality preregistration

Frozen before V2 collected its first observation on 2026-07-21.

V1 proved that Bybit can revise an M5 row after its nominal close. V2 is a new
collector/spec/root; V1 files and receipts remain immutable. V2 changes exactly
one data semantic and adds one online invariant:

- a row is usable only when `bar_start + 10 minutes <= source_as_of`, which is one
  full M5 settlement interval later than V1;
- if the same `(symbol, bar_start)` is ever observed with different normalized
  values, collection stops fail-closed before the new snapshot is persisted.

All universe thresholds, event scoring, 100-symbol prefetch cap, five-minute poll,
seven-day/2016-snapshot/512-MiB bounds, public Bybit GET-only contract, immutable
gzip/hash/delta replay, and no-promotion authority remain unchanged. V2 makes no
credential, private API, broker, order, transfer, account, risk, allocator, or live
router call.

The V1 label-scorer semantics remain frozen. An interim V2 label receipt is not
meaningful until at least 48 hours of valid tape exist (24h horizon plus prospective
signal time); the intended observation is seven days. Any further source revision
stops V2 and requires a separately preregistered V3. It must never be repaired by
choosing first/last rows after viewing returns.
