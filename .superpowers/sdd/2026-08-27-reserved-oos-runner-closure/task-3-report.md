# Task 3 — independent audit and preflight freeze

## Delivered

- Added an independent audit that does not import the one-shot runner. Its
  pre-execution mode validates only pinned metadata, rejects any authorization,
  claim, or result artifact, and never resolves a reserved input `source_path`.
- The post-execution audit independently checks authorization/claim/receipt
  identities, claim-before-decode timing, immutable output inventory and hashes,
  research/live stable-comparator parity, occupancy, metrics, threshold checks,
  and three-way decisions. It validates reported decisions rather than using
  them as an authority.
- Review-fix hardening additionally enforces the runner's complete owner
  authorization and claim-forensic contracts, exact presealed-threshold pin
  linkage, exact on-disk output directory inventory, evaluation-ledger parity,
  and full sleeve evidence equality. The reserved M5 manifest now has an exact
  top-level metadata schema check; it still never resolves any payload path.
- Pinned the controller-created reserved M5 metadata manifest, runner, and
  audit hashes in the diagnostic config, then recomputed its canonical
  fingerprint.
- Regenerated the tracked metadata-only preflight receipt. It is
  `READY_FOR_OWNER_AUTHORIZATION` with no blockers; it reports zero reserved
  market files opened, zero rows decoded, no performance, no live/broker calls,
  no orders, and no money or promotion authority.

## Verification

```text
PYTHONPATH=/private/tmp/bybot_pytest /opt/homebrew/bin/python3.12 -m pytest -o addopts='' -q tests/test_audit_att1_sbr1_reserved_oos_v1.py tests/test_att1_sbr1_reserved_oos_preflight.py
20 passed in 0.20s

/opt/homebrew/bin/python3.12 -m py_compile scripts/audit_att1_sbr1_reserved_oos_v1.py tests/test_audit_att1_sbr1_reserved_oos_v1.py scripts/preflight_att1_sbr1_reserved_oos_v1.py tests/test_att1_sbr1_reserved_oos_preflight.py
exit 0
```

Focused negatives cover audit self-hash and decision tampering, claim/receipt
timing inversion, ledger mismatch, and missing output inventory. Preflight
tests keep the no-market-open/row-decode assertions and verify missing
manifest, runner, or audit freezes block fail-closed.

Independent review then found eight post-execution validation gaps. Commits
`5a7f3ab` and the follow-up test closure added exact authorization and claim
contracts, frozen threshold linkage, actual directory inventory, evaluation
ledger parity, full sleeve-evidence comparison, strict manifest schema, a
complete synthetic post-execution PASS, and integrated rehashed tamper cases.

Final controller verification after those fixes:

```text
tests/test_audit_att1_sbr1_reserved_oos_v1.py
18 passed in 0.21s

Task 1-3 combined focused suite
66 passed in 52.29s

py_compile and git diff --check
exit 0
```

The audit suite also builds a fully synthetic completed one-shot tree with
valid normalized research/live ledgers, authorization, durable claim, exact
output inventory, and signed receipt. `audit_postexecution` returns
`AUDIT_PASS_RESEARCH_ONLY` for that fixture without importing or invoking the
runner and without creating or resolving any reserved input payload.

## Safety status and next gate

No owner authorization, claim, one-shot output, runner execution, reserved
market payload read, network, broker, private API, order, money, or promotion
path was used. The only next gate is a separately created owner authorization;
the one-shot remains irreversible after its durable claim.
