# R&D Focus Rules (Crypto + Forex)

## Scope Split
- Crypto remains primary live stack (`inplay_breakout` + `btc_eth_midterm_pullback`).
- Forex runs as parallel pilot in isolated module (`forex/`), not mixed into crypto live/runtime code.

## Crypto R&D (only 2 directions)
1. Breakout/retest family with stricter quality and execution realism.
2. Trend-follow pullback family with lower trade frequency and stricter regime/session filters.

## Focus Switch Rule
- If during the last 10-14 days no crypto candidate passes both `base` and `stress`,
  shift 50% of R&D effort to Forex.

## Capital Separation
- Crypto live capital is isolated.
- Forex pilot uses separate test capital and separate reporting.
- No shared risk allocator between crypto and forex until pilot is validated.

## Pass/Fail Criterion (research gate)
- Candidate is considered "pass" only if:
  - `base`: net > 0
  - `stress`: net > 0
  - no catastrophic drawdown behavior

## Operational Note
- Diagnostics windows are not interrupted by R&D deploys.
- Live changes are applied only after scheduled diagnostics snapshots.
