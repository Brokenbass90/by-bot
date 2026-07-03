# Structure/FX screening fast-fail — 2026-07-03

## Verdict

Do not spend more compute on raw BOS/CHoCH or naive FX session-range-fade in the
current form.

These were screening runs, not promotion gates. They were stopped early because
the first blocks were already materially negative and broad across symbols.

## Crypto structure_break

Initial broad BOS-long screening:

- `bos_long_rr1.5_sl0.8_h12_b0.05_cd5`: 3096 trades, `-939.70R`, PF `0.60`, positive symbols `0/12`
- `bos_long_rr1.5_sl0.8_h12_b0.10_cd10`: 2501 trades, `-711.53R`, PF `0.62`, positive symbols `0/12`

Initial BOS-short screening:

- `bos_short_rr1.5_sl0.8_h12_b0.05_cd5`: 3207 trades, `-573.87R`, PF `0.75`, positive symbols `0/12`
- `bos_short_rr1.5_sl0.8_h12_b0.05_cd10`: 2739 trades, `-515.56R`, PF `0.73`, positive symbols `1/12`

Initial CHoCH-short screening:

- `choch_short_rr1.5_sl0.8_h12_b0.05_cd5`: 1376 trades, `-205.94R`, PF `0.78`, positive symbols `1/12`

Interpretation: raw structure_break is frequent, but the raw signal is negative.
Future work needs a quality/regime filter before screening, not another raw
grid.

## FX session_range_fade

Initial EURUSD screening:

- `session_range_fade rr=1.0 sl=0.8 hold=60`: 1111 trades, `-3061.06R`, PF `0.00`
- same result at hold 120 before the run was stopped.

Interpretation: naive FX range fade is not a candidate. If FX continues, it
needs a different structure: session breakout/retest with real signals, trend
pullback with less strict trigger, or round-level/liquidity sweep after data and
signal-count audit.

## Action

- Stop current raw screens.
- Do not promote anything from these runs.
- Next research should focus on:
  1. candle coverage/backfill gate for range/pila before any live risk;
  2. ATT1 decision_bus + edge_monitor wiring;
  3. range/bounce repair only after candle coverage is solved;
  4. FX setup audit before more sweeps, because several current FX setups emit
     zero signals on majors.
