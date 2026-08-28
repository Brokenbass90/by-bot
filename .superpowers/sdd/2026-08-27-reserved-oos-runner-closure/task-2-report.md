# Task 2 — reserved OOS runner closure

## Delivered

- Added `scripts/run_att1_sbr1_reserved_oos_v1.py`: a fixed-path,
  fail-closed one-shot runner with owner-authorization validation, immutable
  source/manifest pin checks before market payload access, exclusive durable
  claim creation, atomic terminal receipts, and no CLI override flags.
- The runner validates each reserved M5 identity and payload before invoking
  the unchanged live-native sleeve boundary. It applies the frozen economics
  occupancy/metrics primitives and records the three-way decision contract in
  the successful receipt.
- Added focused tests for authorization-before-open, durable claim ordering,
  second-attempt refusal, consumed attempts on payload drift, decision
  boundaries, and the fixed CLI surface.

## Verification

```text
PYTHONPATH=/private/tmp/bybot_pytest /opt/homebrew/bin/python3.12 -m pytest -o addopts='' -q tests/test_run_att1_sbr1_reserved_oos_v1.py
11 passed in 13.77s

/opt/homebrew/bin/python3.12 -m py_compile scripts/run_att1_sbr1_reserved_oos_v1.py tests/test_run_att1_sbr1_reserved_oos_v1.py
exit 0

git diff --check
exit 0
```

## Safety status

- No owner authorization was created or modified.
- No reserved market payload, network, broker, live/private API, order, money,
  or promotion path was accessed.
- The real CLI was not invoked. In the present checkout its frozen metadata
  still lacks the separate owner authorization and cannot proceed.
- An unrelated untracked reserved input manifest may be materialized by the
  external controller; it was not inspected, changed, or staged by this task.

## Next gate

An owner must separately freeze the audit/runner/manifest pins and create the
exact authorization before any one-shot execution is considered. A claim is
irreversible: any post-claim failure remains consumed and fail-closed.

## Independent review fix round 1

- Repaired the scoring boundary so every signal sleeve receives exactly the
  final 200 preholdout H1 bars plus reserved H1 bars, while BTC regime evidence
  is continued from the full causal preholdout history and restricted to
  reserved close timestamps. No reserved-window EMA reseed or first-200-hour
  drop is allowed.
- Bound the in-memory view to the reserved input-manifest SHA and its exact
  data bundle; preholdout `data_files` are excluded from the scoring view.
- Added pre-claim output/claim symlink and stale-artifact refusal; exact scorer
  inventory; richer success/failure forensic receipts; and catchable
  interruption terminal receipts.
- Enforced the materializer's exact payload/record contracts, including its
  producer `canonical_sha(records)` implementation. The producer adds a final
  newline to canonical JSON bytes; the focused regression test calls that
  producer rather than duplicating the hash convention.

Verification after fix round 1: focused suite `18 passed in 26.49s`,
`py_compile` exit 0, and `git diff --check` exit 0. The CLI was not invoked;
no authorization, real payload, network, broker, or live path was accessed.

## Independent review fix round 2

- Removed the runner's runtime import of the unpinned materializer. Its local
  record-hash helper mirrors the producer contract; a focused test compares it
  against the producer at test time.
- Replaced the contradictory copied live-manifest view with the explicit
  `att1_sbr1_reserved_oos_scoring_view_v1`, carrying exact source-candidate and
  reserved-input identities plus only the frozen scoring bundles.
- Excluded the terminal H1 bar closing at `END_MS` from all decision H1 views.
  The full reserved M5 series remains available for outcome paths.

## Independent review fix round 3 (partial)

- Runner now records reserved input decode identities incrementally and exposes
  bootstrap decode identities/timing from the production scorer. Terminal
  failure receipts retain classification, terminal time, partial decode
  accounting, and hashes of safe partial expected artifacts.
- The scoring-view source candidate identity is the exact frozen config file
  SHA in production. Row validation mirrors the Task-1 producer: OHLC must be
  finite and positive; volume/turnover are numeric finite values and may be
  zero.

## Independent review fix round 4

- Added outer-identity rebinding for schema/window/gap/record-hash/OHLC drift
  fixtures, while keeping raw file-hash drift separate. Each path now reaches
  its intended post-claim failure invariant.
- Added the pure warm-prefix preparation boundary test: 200 preholdout H1
  bars, first reserved H1 at index 200, continuous BTC regime timestamps, and
  half-open terminal-H1 exclusion.

## Independent review fix round 5 (partial)

- Production scorer now delegates its H1/M5 warm-prefix and regime preparation
  to the tested pure boundary. Bootstrap accounting is initialized and updated
  per decoded file, so a later bootstrap failure retains earlier identities.

## Independent review fix round 6

- Reserved decoding now records opened bytes/SHA, JSON decode, observed rows,
  validation state and the exact failure for every attempted symbol. A semantic
  failure can no longer under-report already decoded rows.
- Bootstrap decoding is factored into the production path with incremental
  per-file accounting. A forced second-file failure proves the durable claim,
  partial bootstrap inventory and top-level decode end remain consistent.
- Terminal receipts inventory every observed output entry without following
  symlinks, including unexpected files that caused exact-inventory refusal.
- A capture test proves the production scorer calls the exact tested
  200-H1/half-open preparation boundary once and passes the returned market and
  regime objects unchanged to both ATT1 and SBR1 sleeves.

Fresh controller verification after round 6: focused suite `26 passed in
43.08s`; `py_compile` and `git diff --check` both exited 0. The real CLI,
owner authorization, claim, reserved payloads, broker, network and live paths
were not invoked.
