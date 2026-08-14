# ATT1 momentum-stall exit challenger V1

Frozen before the run on 2026-08-14. Research only; no live or promotion authority.

## Question

After ATT1 has already reached its 1R protection threshold, does closing the
remaining position when volume fades and price stops making progress retain
more R than the current ATR trailing runner?

This is not a TP2-distance sweep. TP1, TP2, break-even, and trail settings stay
fixed. The challenger adds one causal exit mechanism with the existing default
volume-fade parameters; no parameter was selected from this dataset.

## Arms

1. Champion: current Geometry V2 exits, volume-stall exit disabled.
2. Challenger: unchanged champion plus volume-stall exit enabled only after
   break-even has armed at 1R. A signal requires an earlier volume impulse,
   recent volume below 0.70 of baseline or 0.45 of peak, and no new progress
   over the three-bar impulse window.

## Frozen contract

- universe: BTC, ETH, SOL, ADA, LINK, DOT, AVAX, SUI perpetuals;
- window: 2024-03-01 through 2025-09-30; sealed holdout remains unread;
- signal: H1; execution and exit observation: causal M5 bars;
- entries: next M5 open; stop-first same-bar ordering;
- costs: 6 bps fee plus 2 bps slippage per side;
- max positions: 3; short only; Geometry V2 pivot-sequence profile;
- champion exits: TP1 1.2R/55%, TP2 2.5R, BE/trail activation 1R,
  ATR trail 1.5;
- stall exit defaults: baseline 20 bars, impulse 3 bars, fade 0.70,
  peak fade 0.45, price stall required, BE armed required.

## Decision

The challenger is useful only if:

1. net R/trade and PF(R) both improve;
2. it does not add more than two red months;
3. the gain is not produced by one symbol;
4. at least ten VOL_FADE exits occur, otherwise the mechanism is not measured.

Any result remains pre-holdout research. No live mutation follows from this run.
