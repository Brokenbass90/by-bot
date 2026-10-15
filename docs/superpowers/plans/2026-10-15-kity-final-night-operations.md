# KITY final night operations — implementation plan

> Execute inline under the owner's attached operational request. Root review
> only; no independent-review retry. Exact monetary GO remains separate.

**Goal:** one separately namespaced, owner-approved final-night micro experiment.
**Architecture:** reuse bounded V2.1 entry and V2.2 recovery; original physical
account lock/wire/heartbeat remain shared, old experiments are immutable pinned
predecessors. Replace the current KITY process, never run a second writer.
**Spec:** owner attachment debb7f7d-588c-47e9-b666-d94b1b3da8b8, October15.

## Constraints

Exact existing ten symbols;215gross/15immediate loss trigger/accepted overshoot/
30min from first durable intent/50bps/10min/20.3% rounding unchanged. No research,
strategy inference, C1–C3 changes, foreign ownership or unrelated process changes.
Terms are a personal owner action; one fresh exact GO, no automatic repeat.

## Tasks

- [x] Verify predecessor accounting/flat/current source custody read-only.
- [x] Tests first: filled terminal predecessor pins, separate control namespace
  with original lock/wire/heartbeat, missing state fail-closed; actual terminal
  clears money mode only when flat/cost-complete. Empty successful error list
  normalizes to None, nonempty error is retained.
- [x] Extend only bounded owner plumbing and GET transport for documented
  account-instrument availability. Keep original configs/source kits unchanged.
- [x] Read-only all-ten account-instrument capture; compare documented fields
  with public specification. Availability is not proof of create acceptance.
- [x] Targeted regressions + source diff/replay; source freeze. Prepare immutable
  kit/config/unit and scoped single-writer upgrade with fresh flat/original lock.
- [x] Independent no-notify health must be HEALTHY/ORDERS_OFF before PREPARE.
- [ ] After owner confirms personal terms action: one final PREPARE, show exact
  hash/expiry/quantities/bands/gross/remaining gates; request one exact GO.
- [ ] After GO: immediate one-shot queue, no rehearsal/engineering between GO
  and transport. Existing supervisor handles protection/failure unwind/30min.
- [ ] Independently verify flat, fills, actual costs/funding, native state and
  journal; terminal PASS only if complete10/protection/lifecycle, otherwise
  FAILED_SAFE_FLAT with cause. Final mode ORDERS_OFF/HEALTHY; no new proposal.

## Review focus

No shared-lock replacement or second writer; no predecessor journal mutation;
no false permissions from GET; no terminal health masking unknown fills/costs;
no retry after uncertainty; no reused approval or TTL extension.

## Actual stopping point

V3 installed18:39:23UTC,169targetedPASS, no new intent/GO/POST. Owner explicitly
asks read-only/no orders; opening the intended subaccount UI also shows no
agreement prompt. Official Sign Agreement docs bind metals/stock-perp acceptance
to the master account; checked GETs do not confirm acknowledgement. The signing
POST was not called. Remaining tasks above are pending personal terms resolution
and separate fresh exact GO, not permission to continue money operations.
See reports/KITY_FINAL_NIGHT_READINESS_2026_10_15.md.
