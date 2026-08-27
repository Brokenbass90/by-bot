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
