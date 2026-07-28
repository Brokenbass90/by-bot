# Independent audit: Claude support-bounce package

Date: 2026-07-28

Verdict: **BLOCKED before shadow; exploratory evidence only.**

No live code, risk, order, broker state, or Claude-owned file was changed by
this audit.

## What reproduced

- The saved BTC/ETH summaries contain 102 rows and aggregate `+16.35` over the
  three selected windows.
- The saved alt summaries contain 190 rows and aggregate `+19.76`.
- The standalone six-alt run contains 46 trades, PF `1.746` and net `+11.69`.
- The four proposed archive strategies have the reported historical aggregate
  counts and zero positive-family rate in
  `reports/CLAUDE_STRATEGY_AUDIT_DATA_2026_07_27.json`.
- Backtest fallback can import those four strategy modules from the archive.

These are arithmetic/replay facts, not an untouched OOS or promotion verdict.

## Binding defects

1. The candidate called “ASB1 long” in the handoff is actually
   `alt_support_bounce_v1` / `BOUNCE1`. Live ASB1 refers to a different short
   slope-break strategy. The current catalog contains conflicting aliases.
2. `BOUNCE1_RISK_MULT=0` does not create a virtual trade lifecycle in the
   current live flow: sizing becomes zero and the handler returns. Therefore a
   nominal risk-zero enable cannot collect 20–30 shadow closures.
3. The two selected alt windows share 14 trade identities. The claimed 292
   rows across six windows contain 278 unique trades.
4. The parameters and regime windows were selected using the same evidence.
   The result is not an untouched holdout.
5. The claimed power threshold is not met: the 46 saved trade returns imply
   power around `0.475` and an estimated requirement near 114 trades under the
   audited helper assumptions.
6. `TP1_FRAC=0.0` was not actually tested because the strategy clamps it to a
   minimum of `0.1`.
7. The two sighting shell scripts contain hard-coded `/sessions/...` paths,
   inherit ambient environment, and do not emit a complete effective-env/source
   hash receipt.
8. `research_lab/significance.py` is a useful base, but effective independent
   `n_trials` and cross-trial dispersion are not known; it also treats N=1 as
   N=2 and has no focused tests.
9. Archive moves are not ready to commit. Registry/system-manifest discovery
   scans `strategies/*.py`, while saved autoresearch references still point to
   active module locations.

## Required next contract

- Canonical candidate id: `support_bounce_v1` / `BOUNCE1`, never ASB1.
- Freeze full effective env, source SHA, data hashes, costs and untouched
  chronological windows before replay.
- Add a research-only virtual decision → fill/non-fill → exit ledger that
  cannot place orders and does not depend on non-zero live risk sizing.
- Require non-overlapping folds, minimum sample from an explicit power rule,
  cost stress, side split, symbol concentration and forward execution parity.
- Keep the existing live ATT1 champion and all live risk unchanged.

The archive proposal remains reversible research cleanup and is blocked until
registry/config/reference mapping is archive-aware.
