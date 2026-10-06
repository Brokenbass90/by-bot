# Alpaca DAY re-arm and trailing — October 6

**REARM_AND_MONOTONIC_TRAILING_PASS**, broker postcheck **15:10:58 UTC /18:10 Cyprus**.
Machine receipt: `ALPACA_DAY_REARM_2026_10_06.json`. Initial postopen capture was
14:59:24 UTC; independent GET-only postcheck confirms full remaining-quantity
native DAY protection. No broker write, configuration change or manager restart
was made by this cycle. Account suffix f295c6, cap $487.42/gross0.70 unchanged.

| Position | Remaining quantity | Entry | Broker mark at postcheck | Accepted DAY stop | HWM |
|---|---:|---:|---:|---:|---:|
| CRWD | 0.469970151 | 265.336 | 282.54 | **275.45** | 285.455 |
| META | 0.141939508 | 724.534 | 740.68 | **668.76** | 746.49 |

CRWD active stop `43d0807d-b95d-4c54-8fa0-34112d902f4a`, submitted13:50:12.703UTC.
META active stop `c7df017d-4448-4673-b90a-fa8c5a4b44c4`, submitted13:30:10.706UTC.
Both broker status `new`, sell-stop, DAY, remaining order quantity exactly matches
the corresponding position. Accepted IDs agree with persisted ownership/floors.

CRWD's broker-linked replacement chain today is
**242.13 →267.82 →272.13 →273.11 →274.37 →275.45**, with reciprocal
`replaces`/`replaced_by` links. The current floor is above entry. Floor/HWM never
fell between preopen, initial postopen and final postcheck. META HWM gain is only
3.030362%; the existing frozen activation is3.5%, so `trail_not_armed` is expected.
CRWD latest manager reason is `no_material_stop_raise`, not a missing stop.
Frozen trailing distance3.5% and minimum lock0.5% were not changed.

Exactly one NEW flock-protected five-minute schedule remains; OLD managers are
absent. All58 deployed source pins match manifest73345c03…f0fbb2. Runtime latest
management receipt15:10:14UTC agrees with broker IDs and unchanged binding.
Protection from the exact opening instant remains **NOT_PROVEN**: first DAY
re-arm submission was roughly10seconds after13:30UTC open. Stops can gap/slip;
this receipt proves accepted protection, not a guaranteed realized profit/loss.
DAY expiry still requires the existing next-session manager re-arm. Queued
fractional next-session protection remains a separate PAPER gate.

## AMD realized fee followup

The complete published activity page before14:54:26UTC cutoff contains the sole
October5 AMD full sell0.186377282 at622.312. Gross+$2.374819327244. Broker has now
published October5 CAT−$0.01 and REG−$0.01: **+$2.354819327244 after published exit
fees**. Pending REG/TAF and accrued fees read zero. October1 entry CAT−$0.01 was
pooled across three buys; exact AMD allocation is NOT_PROVEN. Full lifecycle
exact net remains **ALLOCATION_PENDING**, rather than inventing a per-leg split.
Published-fee-only allocation range is+$2.344819327244 to+$2.354819327244; this is
not a bound on future unreported liabilities.

## Continue

Current monthly entries/selection, risk and protection remain frozen. Immediate
replacement after AMD exit is not enabled. `ALPACA_DYNAMIC_REPLACEMENT_V1_PLAN_2026_10_06.md`
is SCOPED/NOT_IMPLEMENTED/NOT_TESTED/NOT_PREREG_FROZEN: A frozen monthly reserve
replacement and B weekly refresh must face identical historical/holdout capital,
risk and costs, then PAPER before promotion. AI remains diagnostics/proposals.
Next daily operational check: October7 regular open13:30UTC/16:30Cyprus, exact
remaining quantities, accepted stop IDs and monotonic floors/HWM/single manager;
never rerun an initial-flat activation.

Private raw SHA256 pins, assertions and public non-secret fields are in JSON.
Verification: initial acceptance plus final postcheck assertions in
`.private/owner_close_20261006/accept_alpaca.py` and `finalize_receipts.py` PASS.
