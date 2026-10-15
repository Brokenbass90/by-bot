# Alpaca NET trailing — October 15, read-only verification

**TRAILING_ACTIVE_AND_BOUND**, observed 2026-10-15 14:43:05.588 UTC
(17:43:05 Cyprus). This means the installed owned manager calls the ratchet;
the activation threshold has **not** been reached. No stop change was made by
this observer.

Actual broker state: NET quantity **0.325167779**, entry **311.222 USD**,
position mark **310.2494 USD**. One native sell STOP/DAY, order
`28ecadfb-376d-4e4f-b34f-40e5fd16843c`, status `new`, full quantity,
stop **277.69 USD**, filled quantity zero. Durable phase `PROTECTED`, exact
intake/stop lineage and full remaining coverage matched. Persisted HWM
**315.505 USD** (peak gain **1.376188%**), accepted floor **277.69 USD**.
Last manager service completed **14:40:03 UTC**, exit 0; `inactive` is the normal
between-ticks state of this timer's oneshot service, not a dead recurring manager.

## Exact installed rule

Every five minutes during the regular session, the owned manager samples
`position.current_price` and persists `HWM = max(previous HWM, sampled mark)`.
This is a software ratchet of a native fixed stop, not a broker-native trailing
order and not continuous observation of every market high.

Frozen parameters: activation gain **3.5%**, trail **3.5%**, minimum lock gain
**0.5%**, minimum raise **10 bps**, market gap **10 bps**. At activation:

`target = floor_to_tick(min(max(old_stop, accepted_floor, HWM*0.965, entry*1.005), current_mark*0.999))`.

A replacement is permitted only if target is at least `old_stop*1.001`.
Accepted protection never intentionally downshifts. Below the accepted floor
the existing path escalates to scoped unwind rather than lowering protection.

Entry **311.222** gives the exact activation price **322.114770**. Examples
computed by the **installed pure function in RAM**, assuming observed mark equals
HWM, cent-grid marks and no intervening market retreat:

| First sampled HWM at/above | Old stop | Proposed new stop |
| --- | --- | --- |
| 322.12 | 277.69 | 312.77 |
| 324.45 | 312.77 | 313.09 |
| 324.78 | 313.09 | 313.41 |
| 325.11 | 313.41 | 313.73 |

These are conditional calculations, not broker replacements or guaranteed
future fills. Legal tick rounding makes the first floor approximately 0.5%
above entry, before costs; it is not an exact net-profit guarantee.

## Recovery and limits

- Restart preserves HWM, accepted floor, ownership and durable replacement
  identity. An uncertain PATCH is reconciled by explicit `replaces` lineage;
  it is not blindly resent. Confirmed floor/quantity/readback must match.
- A partially filled stop continues protecting the proven remaining quantity;
  this branch does not ratchet the partially executing order.
- DAY expiry is handled by the existing owned re-arm path, retaining accepted
  floor; it does not reopen the entry or adopt other positions.
- **Source limitation:** maintenance uses the broker position mark without an
  independent exchange timestamp for that mark. Its fresh broker-clock check
  is not proof of mark freshness. The entry quote CTS gate does not establish
  such a maintenance check. No stale-mark protection is claimed here. Record
  this for a separately reviewed future version; do not hot-change this live
  position, strategy or stop.

All **53** installed static pins verified. Installed runtime SHA256
`05166883fbedecad1ab55a01bc28d00714b4e1fce9e86bb706997dd9a6656530`,
ratchet SHA256
`2d5243ee52d3857c14fd564cea671f8938dd1cdc7623f360293154c8bce5eea1`.
Private GET-only capture:
`/opt/bybot-research/alpaca-dynamic-live-20261013/observations/trailing-1792075385588.json`,
SHA256 `4d3c53fa171e20405612f4c0270c60b527014fdc48e352b32a8d54ffb26cbbf0`.
Native ledger bytes were unchanged during the successful observation.
Observer performed zero broker writes, native-state writes, unit/source/stop
changes. Two earlier operator-only lookup/output-path errors produced no
completed receipt and no trading/state changes; they are not runtime failures.
