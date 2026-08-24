# Alpaca health auditor bridge-freshness fix — 2026-08-24

**Authority:** read-only observability hotfix; no order or money-authority
change.

- source commit: `22544e1`;
- root cause: the live bridge writes its causal completion timestamp in
  `broker_truth_after.generated_at_utc`, while the auditor only accepted a
  top-level `generated_at_utc`; protection could be healthy while the sensor
  emitted a false `alpaca_bridge_stale` critical issue;
- regression: the manifest collector test now uses the real nested receipt
  shape;
- focused verification: 17 tests passed, plus `py_compile`, shell syntax and
  diff checks;
- deployed auditor SHA-256:
  `963d55b776821dd254569a51296c4a963f68546aad30c8ee245a589bd6ec64d4`;
- deployed manifest SHA-256:
  `9b4e43df4fcf03867b73b46a4d4bd712ef12cee1ffcb3e5a58f736347cc1d7de`;
- rollback directory:
  `/root/by-bot/runtime/deploy_backups/alpaca_health_bridge_freshness_20260824T1334Z`.

The immediate post-deployment GET-only audit returned `WARN`, not `CRITICAL`.
Its only issues were the two expected
`fractional_day_stop_not_persistent_across_sessions` warnings. Both live
positions remained fully covered and both monotonic floors were preserved.
