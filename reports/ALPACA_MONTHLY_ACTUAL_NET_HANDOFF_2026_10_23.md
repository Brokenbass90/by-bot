# Monthly: actual NET terminal handoff, 23 October 2026

**Actual terminal inventory sealed; operational activation remains unissued.**
The previous cutover packet's missing NET terminal input is now filled from the
actual independent broker capture. This report supersedes its prospective NET
sale instructions; the personal exit is spent and must never be repeated.

## Completed

The existing `read_legacy_transition` and `legacy_transition_orders` validators
accept the actual buy and full sell, their account/ownership, quantities and
timestamps. Exact entry and exits balance at 0.325167779 shares. Private seal SHA:
`bb5363f3361f8e8230a664488f7aea742490e93be3d0c4173fd3b4b195a2a67d`.
The seal remains private because it contains original account/order evidence.
[Sanitized validation receipt](evidence/monthly_cutover_20261023/terminal-review.json).

The existing false-authority review envelope was refreshed with this exact seal,
the spent exit status and a retirement proposal. All 53 accepted Monthly sources
are unchanged; the standing scope still uses its exact 45-file closure.
Budget remains capital400 / gross280 / reserve40 / maximum4 positions /
single-entry168 / entry loss-admission8 / no new borrowing. Loss admission
inhibits new BUY and preserves custody; it is not a guaranteed maximum loss.

The full production CLI also passed a **local synthetic rehearsal with these
exact budget limits**, using the unchanged selector and source loader: 58 source
symbols, eight CLI calls, two simulated entries, one rotation exit, two simulated
retirement checks, recovery of lost entry/stop/replacement responses, zero
duplicate entries, pending fees during replacement and final reconciliation.
[Acceptance](evidence/monthly_cutover_20261023/owner400-local-acceptance.json),
[exact fixture driver](evidence/monthly_cutover_20261023/rehearse-owner-budget.py),
[fixture change review](evidence/monthly_cutover_20261023/fixture-review.json).
The first fixture attempt failed because synthetic scope capital `400` did not
match the existing canonical `400.0`; only the fixture spelling was corrected.
The earlier failures are retained. No production limit or source was relaxed.
This additional budget rehearsal ran locally; earlier unchanged component VPS
acceptance is not presented as a VPS run of this new fixture. Its synthetic
weekday calendar is not actual XNYS/prospective evidence or a latency benchmark.
Reproduction requires a new exclusive output directory; the saved driver never
loads a real profile and denies socket traffic.

The account context is explicitly dated **23 October 14:02:46 UTC**, not a fresh
entry-window check: flat/no open orders, cash/equity496.31 and pending regulatory
fees0.02. Gross NET result +0.216561740814 before fees is not final net profit.
The terminal seal proves ownership and closure, not final commissions. Pending
fees are neither assumed zero nor automatically subtracted twice.

## Remaining operational transition

| Gate | Concrete action | Why it remains |
|---|---|---|
| Cost/cash binding | Bind actual terminal seal, complete activity source, tariff/calendar/assets and cash anchor to final runner/scope; use existing bounded pending-cost admission where proven | Flatness alone is not a complete final cost context; final runner pins are not issued |
| Legacy retirement | Propose only `disable --now alpaca-oct15-owned-manager.timer`, after fresh flat/terminal/ownership and no unresolved jobs/dispatch; preserve locks, journal, HALT and spent claims | Exact retirement operation is review-only, not executed or separately authorized; do not kill a running service |
| Retirement proof | Existing `capture_retirement` verifies the four financial units, cron/process/source chain and original shared lock; SHOP remains disabled | Old NET schedule still exists; no synthetic retired receipt is allowed |
| Final operational config | Bind the existing nine config fields, original lock identity, exact source closure, native/profile/cost/notification/handoff inputs; hash config before deriving owner scope | The refreshed envelope is a review object, not an executable configuration |
| Standing authority | Owner approves the resulting exact scope, validity and activation operations | Budget approval is preparation authority; no actual Monthly BUY scope was issued |
| Scheduled market facts | Actual 30 October completed57+SPY selection, then fresh2 November entry-window broker/cash/protection/readback | Future observations cannot be produced now; CASH/NO_SEND remains valid |

The existing safety sequence and rollback rules remain in
[the cutover packet](ALPACA_MONTHLY_CUTOVER_PACKET_2026_10_22.md). Do not re-enable
NET automatically after retirement, clear any claims/latches or select a second
manager. A live service rollback is not implemented by the disabled-pointer helper.

PUMP4 implementation proceeds independently while NET fees settle. No new
Monthly financial authority, order, legacy retirement or unit mutation occurred.
