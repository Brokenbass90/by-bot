# Pair-arbitrage review — 2026-06-18

## Accounting correction

The earlier matrix displayed zero metrics because `run_pair_arb_matrix.py`
attempted to convert nested walk-forward aggregates directly to `float`. The
matrix runner now reads the aggregate mean explicitly and uses the canonical
all-trade win rate.

The first corrected report then exposed a second issue: a positive arithmetic
mean and inflated mean profit factor were enough for `PASS`. This allowed folds
with no losses (`PF=99`) to dominate the mean. Promotion now distinguishes:

- `PASS`: fee-robust, positive majority of OOS folds, positive median return,
  bounded worst fold and robust aggregate;
- `RESEARCH`: positive and fee-robust aggregate with enough trades, but not
  stable enough for live promotion;
- `FAIL`: insufficient or cost-fragile result.

## Current candidate

The only useful pocket in the 180-row local matrix is `LINKUSDT/ETHUSDT` with
lookback `336h`, entry/exit/stop z-scores `2.4/0.3/3.5`:

| metric | value |
|---|---:|
| OOS folds | 15 |
| positive folds | 7 |
| total trades | 49 |
| mean OOS return | +1.0611% |
| median OOS return | 0.0000% |
| worst fold | -5.0572% |
| best fold | +10.8847% |
| median PF | 1.0000 |
| fee sensitivity | positive through 12 bps in the current model |
| corrected verdict | `RESEARCH` |

This is not ready for live capital. It is a legitimate shadow/research
candidate because the aggregate survives the modeled fees, but fewer than half
of the folds are positive and the worst fold is material. Before promotion it
needs non-overlapping time validation, realistic hedge sizing, funding/basis,
two-leg fill synchronization and failure/partial-fill simulation.

`SOLUSDT/ETHUSDT` and the remaining positive rows are fee-fragile. The tested
`ETH/BTC`, `DOGE/BTC` and `ADA/ETH` pockets were negative and should not enter
the live package from this matrix.
