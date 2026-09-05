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

Status: not yet deployed. This section will be replaced with exact Git SHA,
enabled-config SHA, manifest SHA, source-closure SHA, target Python/systemd
checks, rollback path, bootstrap receipt, and first scheduled receipt.

Bootstrap rows are `ALPHA_FORWARD_BACKFILL` and do not start the 72-hour
burn-in. Burn-in starts only with the first healthy scheduled
`EXECUTION_FORWARD` cycle.
