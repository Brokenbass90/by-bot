# ATT1 fresh handoff — proposed, orders OFF

Status: `PROPOSED_NOT_IMPLEMENTED`. This is a concrete alternative to impossible
legacy-state reconstruction from the available file/GET sources. It is not an
approved money transition or a substitute for the existing strict handoff.
Evidence: `ATT1_BOUNDED_INPUTS_RESULT_2026_10_03.json`.

## Why the legacy path is blocked

The actual OLD wrapper has no state export API. `_last_tf_ts` and `_cooldown`
belong to individual in-memory strategy instances; journals do not serialize them.
The counter decreases on `maybe_signal` calls, before the H1 comparison, and is
set on signal production rather than proven trade closure. Native pause returns
before engine evaluation. Eight hours of wall-clock waiting cannot prove that
OLD's counter has expired or establish an exact `cooldown_until_ms`.

Restart/replay would produce a new instance, not recover the old PID's values.
Do not enable its currently incompatible caller-receipt seam: the deployed wrapper
does not expose `last_closed_rows`. No attach/injection, restart, OLD resume,
fabricated zeros or wall-clock-as-actual-watermark is proposed.

The six named legacy cash islands are now broker-reconciled: four isolated known
entries and two ADA positions with additional entries. This resolves their
account-level exits/cash, not pure ATT1 attribution for the mixed positions, all
historical intent finality, initial protection continuity or strategy net edge.
Existing journals and contamination labels stay unchanged.

## Recommended explicit cold transition

1. Add an explicit, versioned **fresh-epoch** declaration at the existing handoff /
   route boundary. Keep current legacy continuation validation unchanged. A
   fresh declaration records old state as UNKNOWN and the retirement evidence;
   it must never populate `old_watermarks` with invented recovered values.
2. Retire OLD **entry authority** durably before establishing the epoch. Candidate
   uses the existing `ENABLE_ATT1_TRADING` entry guard plus native pause; verify
   effective config across reload/startup layers, management independence and
   failure/restart behavior before any runtime write. Native pause alone is
   insufficient because absent/damaged control fails OPEN. Keep the service and
   exit/protection management. Require authenticated flat/no-open-orders and a
   complete in-flight intent inventory; any late fill invalidates the transition.
3. Seal an H1 fence from the accepted retirement clock and actual closed-bar
   availability. NEW must reject signal closes at/before that fence. Bootstrap
   the frozen NEW engine from PIT closed data without submitting pre-fence signals.
   Proposed migration quarantine: **96 consecutive closed 5-minute bars after the
   fence**, matching NEW's frozen eight-hour cooldown length. Missing bars extend
   it. This is a deliberate cold migration policy, **not preservation or proof of
   OLD's call counter**. Its adoption needs explicit review/approval; no new
   strategy/profile parameter, live regime filter or public epoch reset.
4. After the fence/quarantine, assemble fresh actual risk/fees/mode/cash/funding
   inputs in the existing builder. Enforce one entry owner, one slot, min-qty /
   min-notional rejection, fixed USDT caps and conservative source-bound costs.
   Require complete current-day cash and outstanding prior-cost coverage; a fresh
   epoch does not erase unknown liabilities. Keep LINK hedge-row conflict and HFT
   missing costs fail-closed until honestly resolved for the execution binding.
5. Persist/replay the declaration and gate decisions atomically in the existing
   coordinator. Missing/malformed declaration, wrong account/code/profile, OLD
   re-enable, missing bars, stale broker truth, late fill or unknown cash denies
   preparation. No NEW transport, money service or production DB migration in
   this proposal. `NEW_READY` remains a preparation state, never order permission.

Acceptance before implementation/deployment: targeted missing-state / damaged-pause /
late-fill / duplicate-H1 / interrupted-quarantine / restart / cash-carryover denial
scenarios and old-receipt oracle preservation; one bounded financial review.
Selected-account dispatch/protection/exit/finality integration remains separately
required. The public gate is still 2–3 clean prospective filled terminals/net-R,
then fresh exclusive dossier and separate owner GO. No calendar promise.

## Funding and mode are separate blockers

Frozen hold is 4032 × 5 min = 14 days. Current funding limits/intervals give a
modelled full-hold shock, not an immutable future ceiling. At the private draft's
full risk reserve R=0.4 / daily cap D=0.8, even the minimum notional 5 USDT plus
the captured OLD-eight funding shocks and two taker fees exceeds remaining
daily cash. This full-risk scenario must be rejected, not made green by higher
risk, shorter hold or latest-rate-only costs. It does not prove every smaller
quantity or all 51 symbols infeasible. No funding reserve policy is approved.

LINK's first complete response includes real zero-size hedge rows 1/2; a later
terminal page adds a placeholder-like index0. Repeating with limit200 preserves
the conflict. Global flat acceptance establishes exposure absence, not one-way
mode for each symbol. Do not silently deduplicate or write broker mode.

## Rollback and next decision

Failure retains NEW orders OFF and OLD entries retired/paused. There is no automatic
OLD resume or rollback over positions. Preserve old and public journals, profile,
source pins and receipts. Future held exposure must retain its owning protection /
exit manager; account-flat is mandatory for a flat rollback.

Next engineering decision is whether to approve this explicit cold migration policy
or require a native legacy-state export instead. Until reviewed and accepted, the
existing actual-account packet remains BLOCKED_DATA. Implementing this proposal
does not itself authorize NEW money or satisfy the prospective cohort.
