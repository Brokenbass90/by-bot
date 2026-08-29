# Codex checkpoint — 2026-08-29

## Outcome

The owner-authorized ATT1/SBR1 reserved diagnostic was executed exactly once.
It created its durable claim before decode, wrote all scorer artifacts and then
terminated `FAIL_CLOSED_AFTER_CLAIM` because the runner summarizer passed tuple
dictionary keys where rows were required. The v1 authorization is consumed and
no retry was made.

The independent failure-forensic audit validates exact input/output inventory,
accounting and parity. It reconstructs the pre-frozen economics without turning
the failed formal attempt into a success: ATT1 is `FAIL_CLOSED` because the
stress second half is `-0.337197R`; SBR1 is `INCONCLUSIVE_LOW_N` at `N=16` and
is negative in base and stress. No live, broker, private API, order, risk,
promotion or money authority changed.

Full publication: `reports/ATT1_SBR1_RESERVED_OOS_RESULT_2026_08_29.md`.

## Completed before execution

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
6. Metadata-only preflight and pre-execution audit both returned
   `READY_FOR_OWNER_AUTHORIZATION`, with zero market files opened, zero rows
   decoded, no performance, no broker/live calls, no orders and no money or
   promotion authority.

## Execution and independent failure forensics

1. Owner authorization ID:
   `owner-authorization-20260829T080646Z-6862987`; authorization commit:
   `9baa5f8`.
2. One-shot claim was written before market decode. Claim SHA:
   `3f3dcf0decaa8352608c2204e9805494ac7fa3d1b17544dd4b95175080a179cb`.
3. The exact failure is `AttributeError:'tuple' object has no attribute 'get'`.
   `read_jsonl()` returned a keyed dictionary and `_summarize_ledgers()` passed
   that dictionary rather than `live.values()` to occupancy.
4. The original success-oriented post-audit correctly refused the terminal
   failure inventory as `BLOCKED_FAIL_CLOSED`; it was not weakened or rewritten.
   A separate read-only failure-forensic auditor was added for this terminal
   state.
5. All 8 reserved inputs (`628,992` rows), all 8 causal bootstrap inputs
   (`1,334,016` rows), and all 16 partial outputs match their frozen hashes.
   Research/live byte parity and normalized comparator parity pass in all four
   base/stress cells.
6. ATT1: base `N61`, `+21.3471R`, PF `1.7921`; stress `N61`,
   `+19.5021R`, PF `1.7030`, halves `+19.8393/-0.3372R`; decision
   `FAIL_CLOSED`.
7. SBR1: base `N16`, `-3.3131R`, PF `0.6418`; stress `N16`,
   `-3.6881R`, PF `0.6080`; decision `INCONCLUSIVE_LOW_N`.
8. Live/broker calls are false, private calls `0`, orders `0`, money and
   promotion authority false. No live deployment occurred.
9. The dedicated failure-forensic suite passes `26/26`; post-authorization
   Task 1–3 regression is `64 passed, 2 deselected`. The two deselected tests
   require owner authorization to be absent and cannot be made applicable
   without destroying the consumed evidence.
10. Final independent verdict after coordinated tamper probes:
    `Spec PASS`, `Code-quality PASS`. CLI fresh-versus-tracked receipt equality,
    `py_compile`, `git diff --check` and the scoped secret scan pass.

## Exact frozen identities

- diagnostic config SHA: `6f4b3b2e5387cf7755617ec0a68ae4e63d4b6cc502332c755eb795117e7eab96`;
- config fingerprint: `302b25fcbb07dd898e2d05ed53aa35f7118eb627b875990153539da726e663fc`;
- tracked preflight canonical receipt SHA:
  `c37d8cfc4b9e1a72f82e0163810bfe402b2fa1bfa1b0d6eae332e74ec7e4f3b8`;
- classification: `RESERVED_OOS_DIAGNOSTIC_WITH_KNOWN_CONTAMINATION`.

The 273-day range is not pristine sealed proof: earlier MPL/XSEC work touched
intersecting H1 data. It is an honest reserved diagnostic with known
contamination, and every sign must be published.

## Next gate

Do not rerun v1. A hypothetical formal v2 would require a new output directory,
claim, config and explicit owner authorization, while preserving v1 byte for
byte. It is not the recommended next spend: the forensic economics already
answer the promotion question.

The next falsifiable work is a preregistered Plan B: bull-continuation and XSEC
PIT rebuild. ATT1 temporal degradation may be diagnosed, but the consumed
window must not be used for parameter selection. SBR1 current geometry gets no
money integration. Alpaca stays on its separate SAFE_HOLD lifecycle gate.

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
