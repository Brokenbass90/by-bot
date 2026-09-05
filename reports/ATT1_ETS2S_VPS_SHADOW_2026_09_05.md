# ATT1 + ETS2S zero-risk VPS shadow — 2026-09-05

## Authority

Public Bybit kline data only. No orders, broker/private APIs, money authority,
performance claims, promotion authority, or changes to existing live services.

## Local evidence

- Canonical L1 parity: ATT1 PASS (`600` decisions, `6` signals, `0` mismatches,
  `0` exceptions); ETS2S PASS (`600`, `30`, `0`, `0`).
- Public cache/Store review: PASS.
- Contract/release/runner/systemd/canonical Store tests: `100 passed` locally.
- Independent final contract/release review: `SPEC_COMPLIANCE: PASS`,
  `CODE_QUALITY: PASS`; no remaining P0/P1 blocker.

## Deployment

Status: deployed, timer enabled, and the first scheduled execution-forward
cycle completed healthy. The 72-hour burn-in started at
`2026-09-05 08:02 UTC` and is due for evaluation after
`2026-09-08 08:02 UTC`.

- Git/release SHA: `773ce065270b5df16041e49e0985c5e950e5da10`
- Minimal release archive SHA256:
  `d676e67fe9c43a709048d0e98148f585cffdaabc408a05e2b834e359780c0c1f`
- Enabled config SHA256:
  `2834c6ffa9e43daa41fdfccb77cda110e25886895cb856a154d710b757a19c0e`
- Manifest SHA256:
  `65b83d60160c4bc86cb577cd7b29fd7c08791534b6ed58287f9e28a09a6eced7`
- Enabled source closure SHA256:
  `896b27c5c570eed8280dbf78050ace180185d4f517573e48eb42c1c23b4bba92`
- Privileged launcher SHA256:
  `ff0cb205b39084d76669f7a0bb0b6fc87f47070e9ef3af6b4b2d77f92b61dc86`
- Target: Ubuntu 24.04.4, systemd 255, `/usr/bin/python3` 3.12.3.
- Target import/preflight and `systemd-analyze verify`: PASS.
- Privilege boundary: launcher `root:root 0755`, deployment anchor
  `root:root 0600`, app `root:bybot-research 0750`, runtime
  `bybot-research:bybot-research 0700`.
- Bootstrap: healthy, 51/51 symbols, 51 ATT1 + 51 ETS2S decisions,
  102 journal rows, 0 exceptions, 0 errors, 0 order/broker calls, all 102 rows
  `ALPHA_FORWARD_BACKFILL`.
- Restart/dedup: healthy, 51 unchanged symbols, 0 new rows; journal remains
  102 rows with tip
  `d16cf90ebfbcb4ecb2b63f99e91a469da07ea1797c45e95bfad7eb5674904c12`.
- First scheduled cycle: service `success`/exit `0`, healthy, 50 ATT1 + 50
  ETS2S execution-forward decisions, 100 new rows, 0 exceptions, 0 errors,
  0 order/broker calls, and all money/private/order authority false. `HFTUSDT`
  had no new closed H1 bar and was correctly deduplicated; it remained in the
  configured and available 51-symbol universe.
- First scheduled signals: ATT1 produced one zero-risk `UNIUSDT` short
  research signal; ETS2S produced none. This is evidence that the signal path
  is live, not evidence of profitability.
- Journal after the scheduled cycle: 202 rows with tip
  `9acbf13164f77f5d37bfdcb9e91d17647f060201e7be0989d1f96bb5454fd1e2`.
- Timer: enabled/active; last trigger `2026-09-05 08:02 UTC`, next trigger
  `2026-09-05 09:02 UTC`. Old ATT1 fixed-51 and SBR1 zero-risk timers remain
  active and untouched.
- Rollback for this first deployment: disable/stop only the new timer and
  service; no predecessor app existed to restore. Files and evidence remain
  preserved for diagnosis.

Bootstrap rows are `ALPHA_FORWARD_BACKFILL` and do not count toward burn-in.
Only the 100 rows from the first healthy scheduled `EXECUTION_FORWARD` cycle
started the clock. No automatic promotion or money gate follows from burn-in.
