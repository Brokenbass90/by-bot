# SDD ledger — plan: docs/plans/2026-08-27-reserved-oos-runner-closure.md

## Pre-flight consistency scan

| Producer task | Consumer task | Shared interface | Finding / ruling |
| --- | --- | --- | --- |
| Task 1 | Task 2 | reserved M5 input manifest and ignored payload paths | Consistent. Runner must accept only the exact schema and frozen major-8 order. |
| Task 1 | Task 3 | manifest SHA and identity-only fields | Consistent. Audit/preflight may hash the manifest, never the referenced market files before authorization. |
| Task 2 | Task 3 | claim, authorization and output receipt schemas | Interface must be frozen in Task 2 tests; Task 3 independently validates it. |
| Task 3 | Task 4 | READY receipt and checkpoint | Consistent. READY is not execution or promotion authority. |
| Task 1 | Task 1 | tests versus no-score materializer | Consistent. Data validation may decode prices; signal/performance imports are forbidden. |
| Task 2 | Task 2 | claim-before-decode and retry refusal | Consistent. Test injection is allowed only through Python function arguments; CLI cannot bypass the real scorer. |
| Task 3 | Task 3 | independent audit versus shared metric primitives | Ruling: shared stable metric primitives may be imported, but the audit must not import the one-shot runner or trust its decision fields. |
| Task 4 | Task 4 | commit/push versus owner authorization | Consistent. Authorization and runner execution are explicitly excluded. |

Ruling: the user's instruction to finish preflight is treated as authorization
for public, no-score M5 materialization only. It is not authorization to create
the owner one-shot release artifact or score the reserved period.

## Task 1 review — fix round 1

- Critical: reused payload schema is not exact; extra top-level/record fields can
  smuggle performance/private data. Fix with exact key sets and tests.
- Important: CLI destination overrides and symlink ancestors permit writes
  outside fixed paths. Fix CLI to fixed paths and validate every ancestor for
  production defaults; retain test-only function injection under temporary
  roots.
- Important: verified reuse rewrites a timestamped manifest and changes its SHA.
  Fix canonical reuse to leave an exact valid manifest byte-identical; rebuild
  only when absent or when explicitly materializing changed inputs before pin.
- Minor: derive millisecond boundaries from UTC strings and assert consistency.

## Task 1 review — fix round 2

- Important: the exported public fetch primitive bypasses acknowledgement when
  called directly. Require an explicit acknowledgement at that primitive (or
  make it private behind a checked token) and cover direct-call refusal.

Task 1: complete — commits `3240c25`, `cb9e28f`, `edb7af9`; final independent
review PASS for spec and quality. Real no-score materialization remains a
controller operation after local verification.

## Task 2 review — fix round 1

- Initial Task 2 review failed on causal EMA warm-state, in-memory manifest
  identity, output/receipt forensics, symlink/stale-output handling, exact
  producer payload validation, and catchable interruption handling.
- Fix round adds continuous BTC H1 warm-state tests, reserved-view identity
  tests, stale/symlink output tests, terminal-interrupt receipts, exact output
  inventory, success receipt coverage, and a materializer-producer hash test.
- The controller manifest remains untracked and untouched. No owner
  authorization or one-shot execution is part of this fix round.

## Task 2 review — fix round 2

- Replaced the unpinned producer runtime import with a local contract helper
  and producer-comparison test; made the reserved scoring view self-describing
  and removed copied sealed-holdout metadata; excluded the terminal closed-H1
  decision at the half-open end boundary.

## Task 2 review — fix round 3 (in progress)

- Added partial reserved/bootstrap decode accounting and audit-complete
  terminal receipt fields. Remaining mutation-fixture rebinding and full
  preparation-boundary integration coverage are still required before final
  review closure.

## Task 2 review — fix round 4

- Rebound synthetic outer identities for semantic payload drift and added the
  pure exact-200 warm-prefix/half-open boundary test.
