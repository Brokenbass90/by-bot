# Final critical review — synthetic exposure core

Reviewed `research_lab/att1_ets2s_lifecycle.py`, its tests, Task 1/global
constraints in the implementation plan, and `task-1-report.md`. Also reviewed
only the UTC alias diff and its five parameterized burn-in test cases.

## Slice blockers

None found. The reducer retains observed unexpected entry quantity and sticky
incidents, distinguishes cancellation request from finality, permits exits
with pending entry or unknown protection, and clamps confirmed coverage on
exit. Terminal eligibility has the specified narrow exposure meaning.
Generated states maintain `held_steps = entry_filled_steps - exit_filled_steps`.
Accepted state collections are immutable; rejection does not mutate them.
Integer coefficients avoid caller Decimal rounding in divisibility, quantities,
and target flooring. No broker, network, subprocess, filesystem, or live
capabilities were found; four authority flags are false.

## Verification

```text
.venv/bin/python -m pytest -q tests/test_att1_ets2s_lifecycle.py tests/test_att1_ets2s_burnin.py -k 'lifecycle or timezone_aliases or unsynchronized_or_non_utc_clock'
28 passed, 29 deselected in 1.55s
```

Additional read-only Python checks passed: 6,000 deterministic candidate event
transitions (`Random(20260906)`, 200 plans × 30 events), independently maintained
integer exposure/finality/coverage expectations, and replay equality after
every accepted transition. Another 1,000 target cases matched a `Fraction`
oracle under Decimal precision 1. These are bounded probes, not full L2 proof.

The burn-in change accepts only `UTC` and `Etc/UTC`; synchronization remains
required. Tests confirm both aliases pass and unsynchronized, missing-zone,
and non-UTC inputs fail closed. No broader L1 suite was rerun.

## Later adapter requirements, not blockers for this slice

Execution identity is strict payload identity, excluding only `event_id`.
In particular, `received_ms` and the original decimal text remain in the
execution fingerprint. Exact reproducible input:

```python
p = ExposurePlan('book', 'ATT1', 'X', 'decision', 'order',
                 'SYNTHETIC_TEST', '0.1', '0.3', 100)
s = apply_event(initial_state(p),
    ExposureEvent('a', 'ENTRY_FILL', 'order', 101, 102, 'x', '0.1'))
apply_event(s,
    ExposureEvent('b', 'ENTRY_FILL', 'order', 101, 103, 'x', '0.1'))
# LifecycleViolation: conflicting execution_id reuse
```

A transport adapter must define stable execution identity versus delivery
metadata and quantity normalization before claiming broker-redelivery parity.
An identical historical execution payload is accepted without rewinding
watermarks; an unseen historical execution is rejected as unresolved ordering.
Profile geometry, price-trigger ordering, protection-cohort cleanliness, L3
accounting, and persisted restart remain separate future gates. This review
does not establish any of those gates or grant promotion/money authority.
