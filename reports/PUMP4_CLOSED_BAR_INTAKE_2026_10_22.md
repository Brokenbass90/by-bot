# PUMP4 V1: durable hourly cursor and cooldown

**CLOSED_H1_CURSOR_COOLDOWN_COMPONENT_PASS, LOCAL ORDERS_OFF.** Exchange
execution/native stops/partial exits and TINY remain **NOT READY**.

## Delivered

`Pump4Intake` connects the unchanged frozen producer to the existing fsynced,
locked `LifecycleJournal` storage in a separate per-symbol file. A PUMP4 domain
check prevents adopting ATT1 events; no ATT1 runtime/evidence is accessed.
The explicit historical seed uses the exact accepted index200 invocation
sequence. Restart replays that seed plus every accepted closed hour, retaining
history and cooldown rather than repeatedly creating an empty strategy.

An identical duplicate returns the same decision ID without appending or
decrementing cooldown. Changed duplicates, old/missing hours, open bars, invalid
clock/OHLC/volume, foreign symbol/domain, PF overrides, source drift and partial
journal tails fail closed. No repair/truncation/reset/seed replacement is done.
Returning a new decision follows fsync; a lost response reconciles persisted
identity. Future order handling must reconcile decision IDs, not assume that
`new=False` proves an order was sent.

## Evidence

- **34 local PASS:**22intake cases +12existing plan regressions, sockets denied.
- **65/65** available frozen fixture signal/plan matches through the new intake;
  **65** restart/identical-duplicate checks preserve journal bytes. One original
  ASTER fixture remains unavailable. These fixtures overlap prior parity proof.
- **54 hourly checks:** ZRO and BLESS, each parent plus26subsequent closed hours,
  reconstructing the intake on every hour and retrying each identical bar.
  Signal values and cooldown match an uninterrupted frozen producer; all24
  cooldown hours suppress signals.54rows are not54new research trades.
- One independent astra/high bounded review identified one P2: after another
  writer commits the same bar and a later bar, duplicate reconciliation could
  return the later decision. A deterministic interleaving regression failed
  before the fix and passes after selecting the requested timestamp. Reviewer
  targeted recheck passed; no unresolved actionable findings. Runtime model/
  effort verified. Root regenerated34tests and65+54parity on final bytes.

[Receipts, source manifest and reproduction](evidence/pump4_intake_20261022/README.md).
No outcomes/PnL/judge, research edits, real broker requests, financial units,
owner grants, NET/SHOP/HALT/locks or KITY claims were changed.

## Next unresolved execution gate

Bind this intake and the accepted reference plan to existing Bybit transport,
native protection/reconciliation and40/60partial exits. Required evidence still
includes partial fills, lost replies, restart/custody, actual instrument minima,
price/quantity rounding, fees/funding and owner-reviewed TINY limits.

This component uses historical/caller-provided clocks, not an authenticated
market source or a proven next-open fill. The full137-symbol opportunity census,
operational feed/restart, exchange execution, VPS deployment/performance and
TINY acceptance are not claimed. Journal capacity fails closed; it never
discards history to continue. No financial GO follows from these tests.
