# Codex checkpoint — 2026-08-29

## Outcome

The frozen ATT1/SBR1 reserved diagnostic is now technically ready for a separate
owner authorization. The materializer, one-shot runner and independent audit
all passed independent review. The one-shot was **not** executed: there is no
owner authorization, durable claim or scored result, and no live/broker/order,
risk or money authority changed.

## Completed

1. Materialized the exact public major-8 M5 identity set for
   `[2025-10-01, 2026-07-01)` under the owner-authorized no-score boundary:
   8 symbols × 78,624 rows = 628,992 rows. Manifest SHA:
   `8f82bb7f6e5fad56e78acb4e9ffe567d2cf045c7901a7e1744a4ad5d12b7434c`.
   No strategy metrics or PnL were computed.
2. Closed the one-shot runner: exact frozen pins, continuous causal BTC H1
   warm-up, half-open reserved window, durable claim before market decode,
   refusal on retry, exact output inventory, complete success/failure forensic
   accounting and no live/private/order path. Runner SHA:
   `9194e5c1e5841ebe9df579b0a15eb4a7fc27ecad3028d2a71eb2af69198b16b4`.
3. Closed the independent audit after three review rounds. It independently
   validates authorization, claim, receipt, thresholds, output hashes,
   compact evaluation ledgers, normalized base/stress ledgers, occupancy,
   metrics and the three-way decision. Audit SHA:
   `da72992ee68c653a4c16274c8f4559caab211217d89e2f9bcd99e8e1b113b9b8`.
4. Final independent verdict: `Spec PASS`, `Code-quality PASS`, no remaining
   Critical/Important/Minor findings.
5. Combined Task 1-3 focused suite: `66 passed in 52.59s`; `py_compile` and
   `git diff --check` passed.
6. Metadata-only preflight and pre-execution audit both return
   `READY_FOR_OWNER_AUTHORIZATION`, with zero market files opened, zero rows
   decoded, no performance, no broker/live calls, no orders and no money or
   promotion authority.

## Exact frozen identities

- diagnostic config SHA: `6f4b3b2e5387cf7755617ec0a68ae4e63d4b6cc502332c755eb795117e7eab96`;
- config fingerprint: `302b25fcbb07dd898e2d05ed53aa35f7118eb627b875990153539da726e663fc`;
- tracked preflight canonical receipt SHA:
  `c37d8cfc4b9e1a72f82e0163810bfe402b2fa1bfa1b0d6eae332e74ec7e4f3b8`;
- classification: `RESERVED_OOS_DIAGNOSTIC_WITH_KNOWN_CONTAMINATION`.

The 273-day range is not pristine sealed proof: earlier MPL/XSEC work touched
intersecting H1 data. It is an honest reserved diagnostic with known
contamination, and every sign must be published.

## Next owner gate

One explicit decision is required: authorize or decline the one-shot. If
authorized, the sequence is fixed:

1. create the hash-bound owner authorization;
2. execute the runner once;
3. run the independent post-execution audit;
4. report `PASS_ZERO_RISK_INTEGRATION_ONLY`, `FAIL_CLOSED` or
   `INCONCLUSIVE_LOW_N` without changing money authority.

Expected runtime is hours, not months. A PASS starts a separate 2-5 engineering
day zero-risk integration/lifecycle gate; it is not automatic permission to
increase ATT1 risk or launch SBR1 with money. A FAIL changes the research queue
the same day. An inconclusive result remains inconclusive rather than being
tuned after seeing it.

## Alpaca boundary

Historical tests can compress most remaining work: PIT/selector replay,
corporate-action/calendar controls, gaps, restart recovery, partial fills,
ratchet monotonicity and whole-share/fractional profiles. They can cover roughly
80-90% of engineering confidence, but cannot prove how Alpaca's actual paper
orders survive real session transitions and broker events. SAFE_HOLD should be
removed only after tested/deployed SHA reconciliation and a clean prospective
`signal → fill → protection → management → exit` paper lifecycle. Current
planning range is 2-4 engineering days for the historical/stress harness plus a
short prospective paper window; 1-2 weeks is a gate estimate, not a promise.

## Target system

The canonical closed loop is:

`idea intake → frozen causal validation → zero-risk shadow/control → allocator + regime governor → degradation monitor → gated release`

AI/Ollama may search, classify anomalies and propose hypotheses. It remains
proposal-only and secret-free. Deterministic code may reduce or disable risk on
a breach; restoring or increasing money authority requires a new receipt and
owner-approved gate. A future learned execution model belongs in a sandbox and
earns authority through the same lifecycle rather than bypassing it.
