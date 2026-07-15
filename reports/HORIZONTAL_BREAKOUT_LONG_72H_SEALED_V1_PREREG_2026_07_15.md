# Horizontal breakout long 72h v1 — sealed successor freeze

**Status:** exactly one research-only successor is preregistered. The sealed
120-day holdout remains unopened and unscored; no performance runner, live
router, allocator, broker call, or risk authorization exists.

## What was frozen

The candidate preserves the sole bounded lead from Pattern Atlas v1:
`horizontal_breakout_long` at `72 H1` on the exact hash-pinned 13-symbol
cohort. A completed H1 bar must open at or below the maximum high of the prior
20 completed H1 bars and close strictly above that frozen level. Entry is the
next H1 open. Exit is the close of the 72nd completed H1 bar after entry.

There is deliberately no retest condition, delayed entry, stop, target,
trailing exit, regime filter, volume filter, AI filter, or parameter scan.
Adding one after seeing the discovery result would change the selected atlas
hypothesis and create a post-hoc repair. Long and short are physically
separate: this freeze contains no short logic.

The same-symbol cooldown is 168 H1 bars and continues through fold boundaries
and embargoes. The future scorer must use complete UTC H1 bars aggregated from
the pinned M5 source and must not fill on the signal close.

## Costs, funding, and partitions

Base execution charges `6 bps` fee plus `2 bps` adverse slippage per side;
stress charges `10 + 5 bps` per side. Long-perpetual funding uses the actual
hash-pinned, symbol-specific settlement schedule for every event from entry
inclusive to exit exclusive. Negative funding credits are set to zero. Stress
charges at least `5 bps` for every funding event; missing or incomplete
funding history blocks performance entirely.

The untouched interval is exactly `2026-03-06 14:00 UTC` through
`2026-07-04 14:00 UTC`. It is split into four fixed 30-day reporting folds.
Entry and exit must both complete inside one fold, and the first 72 H1 bars
after each internal boundary are embargoed. Signals in an embargo still update
the 168-hour cooldown so the evaluator cannot manufacture extra trades by
resetting state.

## Promotion gate

A later one-shot sealed run is a research test, not a live authorization. It
must pass every frozen gate without excluding symbols, folds, or trades:

- at least 100 stress-costed closed trades, base PF at least 1.25, stress PF at
  least 1.10, positive stress net and positive 95%-winsorized stress mean;
- at least 15 stress trades in every fold, with at least 3/4 folds positive and
  median fold PF at least 1.05;
- at least 10 traded and 7 positive symbols, trade-count HHI at most 0.12,
  largest symbol count share at most 15%, top-symbol positive contribution at
  most 35%, and top 10% of trades at most 65% of positive contribution;
- every leave-one-symbol-out result remains stress-net-positive with worst PF
  at least 1.02; timestamp portfolio drawdown is at most 12%; side purity is
  100% long and there are no invalid, censored, or duplicate events.

Any failure is `NO_PROMOTION`. Passing only earns an independent parity review
and prospective paper test; it does not authorize shadow or live trading.

## Integrity-only preflight

```bash
python3 scripts/preflight_horizontal_breakout_long_72h_sealed_v1.py
```

The preflight reads only the frozen JSON/code provenance artifacts. It does
not open raw market snapshots, decode a holdout row, calculate an outcome, use
the network, or write a receipt. Its validated result reports one long
candidate, zero decoded rows, zero opened snapshots, and no performance.

Canonical files:

- `configs/preregistered/horizontal_breakout_long_72h_sealed_v1_20260715.json`
- `scripts/preflight_horizontal_breakout_long_72h_sealed_v1.py`
- `tests/test_horizontal_breakout_long_72h_sealed_v1_preflight.py`

The next permissible implementation step is a separate scorer that exactly
implements this contract and first proves complete funding-history and source
hash coverage. It must be reviewed and frozen before the single sealed run.
