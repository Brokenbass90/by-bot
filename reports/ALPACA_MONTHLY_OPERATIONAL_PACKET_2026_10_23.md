# Monthly — exact operational review packet, 23 October 2026

**READY_FOR_EXACT_OWNER_REVIEW, NOT ACTIVATED.** Actual broker/source inputs and
all nine operational config fields are now bound in private server review files.
No legacy timer was disabled, financial unit installed or Monthly GO created.
This supersedes the incomplete configuration inventory in the earlier handoff.

## Actual result

Fresh nine-GET reconciliation again confirms account flat, no open orders,
cash/equity496.31 and pending regulatory fees0.02. The exact timestamp is retained
in the [sanitized packet receipt](evidence/monthly_operational_packet_20261023/owner-packet-review.json);
it is not an entry-window readback or proof of final NET profit.

The complete source exposed a real software defect: the exact original NET buy
was rejected as `MONTHLY_COST_FOREIGN_FILL`, although the terminal sale was
recognized. Earlier synthetic transition cases started after the legacy buy.
The fix classifies the **exact sealed original entry when its FILL is present**,
while preserving quantity, price, side/symbol, terminal ownership and source
checks. Partial entry fills may precede their order's final `filled_at`. An older
buy outside the source remains supported. Unknown orders still block admission.

Six new cases cover complete/partial entry and foreign-ID/quantity/side/price
conflicts. The regression failed before the fix. The actual complete source now
replays successfully: pending account fees0.02, **legacy0.02, Monthly0**, posted
legacy fees0.01. No fee was hidden, assumed zero or charged to Monthly twice.

**247 tests locally and the same247 on VPS PASS**, zero errors/failures/skips,
53 sources,40 imports, no checkout fallback, network denied. Material:
`86d5c7c7f88433126b69467f9a439eb5be2529da59bf514626892eb8f2e1d8da`.
[Local](evidence/monthly_operational_packet_20261023/local-acceptance.json),
[VPS](evidence/monthly_operational_packet_20261023/vps-acceptance.json),
[source manifest](evidence/monthly_operational_packet_20261023/source-manifest.json).
These are repeated environment checks, not494 independent broker tests.

The exact server **disabled** config also passed the real57+SPY source and
preview for23 October. Repeated binding was idempotent. No month-end selection
was due, no Monthly position existed and no trade was attempted. This is real
source integration, separate from the synthetic financial rehearsal.

## Exact candidate for approval

Private local directory: `.private/money_runner_completion_20261023/monthly-owner-packet-v2`.
Server counterpart:
`/opt/bybot-research/alpaca-monthly-e2e-20261018/candidate-86d5c7c7f8843312-tb149fe05/owner-review-v2`.

| Bound object | Exact value |
|---|---|
| Proposed standing scope file SHA | `3401fc4ccf71334cc446b186306ccf6fe98d11b35e4ae3d66ac9a0bc3852917e` |
| Operational config digest | `ff7399614d108d1616976148af6a93256ef21a96abe3978bc8dbec97f9be1708` |
| Capital / gross / restricted cash | 400 /280 /40USD |
| Positions / single entry / session entry cap | 4 /168USD /4, subject to frozen Monthly selection and weights |
| Entry loss admission | Monthly aggregate realized plus unrealized≤−8USD; durable latch, custody continues |
| Borrowing / NET adoption | No new borrowing; no adoption of legacy NET |
| Proposed new-entry validity | 2Nov2026 14:30UTC through1Feb2027 00:00UTC, **not yet approved** |
| Existing account lock | Original device/inode retained, inode813893 |
| Owner GO | Absent; proposed scope hash is not permission |

All nine fields are concrete: manager, source captures, broker root, original
profile pin, native binding, native options, actual cost inputs/terminal seal,
existing notification channel and legacy handoff policy. Exact standing source
closure is45 files. Broker calendar and58 asset records were obtained via59
bounded metadata GETs. Cost sources retain their real timestamps and provenance.

**Explicit new entry-control decision:** the original legacy HALT exists and
would block Monthly if reused. V1 was therefore not activatable. V2 proposes a
new Monthly-local `ENTRY_HALT.json` in a separate runtime/book with zero owned
positions. This is **new Monthly entry authority requiring explicit approval**,
not a routine fix, old GO continuation or authorization inferred from the budget.
The original legacy HALT remains unchanged at SHA
`30ca600d7d6f98664fc23757ef5520ab5a08a5b5223c6418d3955edcfe51be23`.
Original lock, actual terminal seal, full legacy retirement and exact scope/config/
source checks remain mandatory. No HALT was removed or cleared.

## Approval scope and execution sequence

The review includes exact service/timer templates under `ops-review`.
`systemd-analyze verify` passed on VPS; templates are not installed. They use the
one existing Monthly CLI and a minute timer, not a second manager implementation.
[Exact operations and template hashes](evidence/monthly_operational_packet_20261023/operations.json).

1. Confirm this exact proposed scope, its validity, separate Monthly entry control
   and installation/retirement operations. Budget approval alone is insufficient.
2. Freshly confirm broker flat/terminal ownership, cash/classified pending costs,
   unchanged source/lock/unit pins and no unresolved dispatch or running job.
3. Under the original lock, disable only `alpaca-oct15-owned-manager.timer` and
   let any running legacy oneshot finish. Do not kill recovery, remove claims,
   change SHOP or clear the legacy HALT.
4. Existing `capture_retirement` must prove all four legacy units and the pinned
   read-only cron/process chain. Its fresh proof is checked again before BUY.
5. Install only the reviewed Monthly unit fragments after exact approval. The
   owner personally supplies the exact scope-bound activation; agents do not run
   financial launchers. No Monthly GO or executable personal activation was issued
   in this preparation cycle.

Before any uncertain dispatch, rollback means keeping Monthly entries disabled.
After owned exposure/uncertain dispatch, retain its sole custody and journals and
inhibit new entries. Never automatically re-enable NET or reset latches/claims.

## Only future observations, not engineering waiting

The actual30 October completed selection and2 November fresh account, native
protection, source, cash/cost and ownership checks cannot be attested today.
Existing bounded pending-cost admission is available; final NET commissions are
not an arbitrary waiting condition. CASH/NO_SEND is valid. No date carry,
guaranteed purchase or profit is implied.

One bounded independent review found no additional Important/Critical defect in
the legacy-entry fix or initial packet. V2's explicit entry-control proposal was
root-verified, not independently signed off. See the shared
[review disposition](evidence/pump4_server_20261023/review.json).
