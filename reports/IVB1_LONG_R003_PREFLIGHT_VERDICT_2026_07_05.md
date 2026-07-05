# IVB1 long r003 preflight verdict — 2026-07-05

## Context

Reason for this run:

- Live crypto portfolio is too narrow: only `ATT1 short-only` is risk-bearing.
- Current live regime is `bull_trend`, so a bull-side / long momentum sleeve is the correct next gap to investigate.
- IVB1 long smoke on the ATT1 base universe showed a positive pulse:
  `20 trades`, `+2.86R`, `PF 1.579`, `DD 1.87R`.

## Candidate

Strategy:

- `impulse_volume_breakout_v1`

Side:

- long-only

Universe:

- `BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,LTCUSDT,DOTUSDT,SUIUSDT`

Best preflight row:

- `r003`

Parameters:

```env
IVB1_ALLOW_LONGS=1
IVB1_ALLOW_SHORTS=0
IVB1_REGIME_MODE=off
IVB1_BREAKOUT_LOOKBACK_BARS=24
IVB1_IMPULSE_LOOKBACK_BARS=18
IVB1_VOL_PERIOD=20
IVB1_MIN_BODY_FRAC=0.45
IVB1_MIN_BAR_RANGE_ATR=1.2
IVB1_RECLAIM_ATR=0.08
IVB1_ENTRY_BODY_MIN_FRAC=0.25
IVB1_TOUCH_BELOW_BREAKOUT_ATR=0.20
IVB1_INVALIDATION_CLOSE_ATR=0.35
IVB1_TP1_RR=0.9
IVB1_TRAIL_ATR_MULT=1.4
IVB1_TRAIL_ACTIVATE_RR=0.9
IVB1_MIN_STOP_PCT=0.008
IVB1_MAX_STOP_PCT=0.060
IVB1_TIME_STOP_BARS_5M=72
IVB1_COOLDOWN_BARS_5M=12
IVB1_MIN_IMPULSE_PCT=0.04
IVB1_MIN_VOL_MULT=1.4
IVB1_SL_ATR=1.0
IVB1_RR=1.6
IVB1_RETRACE_MAX_FRAC=0.50
```

## Results

### Preflight sweep

Run:

- `backtest_runs/autoresearch_20260705_043524_ivb1_long_bull_current360_preflight_20260705`

Outcome:

- 32 rows tested
- 9 rows passed the basic preflight constraints

Top row:

| row | trades | net | PF | WR | DD | red months |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| r003 | 29 | +6.47R | 2.791 | 72.4% | 1.67R | 2 |

### Execution-accurate next-open check

Run:

- `backtest_runs/portfolio_20260705_110205_ivb1_long_r003_nextopen_20260705`

Result:

| execution | trades | net | PF | WR | DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| next-open, 6/2 bps | 29 | +6.47R | 2.791 | 72.4% | 1.59R |

### Fee/slippage stress

Run:

- `backtest_runs/portfolio_20260705_110647_ivb1_long_r003_nextopen_stress_20260705`

Result:

| execution | trades | net | PF | WR | DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| next-open, 10/5 bps | 29 | +5.28R | 2.338 | 72.4% | 1.72R |

### Time-fold check

Using `wf_folds` + `oos_selector` on r003 trades:

- base: PASS, `4/4` positive folds, `28` used trades, reason `robust_plateau`
- stress: PASS, `4/4` positive folds, `28` used trades, reason `robust_plateau`

Base folds:

```text
fold0 +1.70R / 6 trades
fold1 +1.91R / 11 trades
fold2 +1.41R / 6 trades
fold3 +1.18R / 5 trades
```

Stress folds:

```text
fold0 +1.56R / 6 trades
fold1 +1.45R / 11 trades
fold2 +1.07R / 6 trades
fold3 +0.98R / 5 trades
```

### Symbol-OOS check

Same r003 params on an external symbol basket:

- `DOGEUSDT,XRPUSDT,AVAXUSDT,ATOMUSDT,BNBUSDT,BCHUSDT,XLMUSDT,1000PEPEUSDT,HYPEUSDT,TAOUSDT,ONDOUSDT`

Run:

- `backtest_runs/portfolio_20260705_105347_ivb1_long_r003_symbol_oos_20260705`

Result:

| trades | net | PF | WR | DD |
| ---: | ---: | ---: | ---: | ---: |
| 58 | -0.22R | 0.985 | 56.9% | 3.47R |

Fold verdict:

- FAIL, `2/4` positive folds, reason `unstable_frac_pos_0.50`

## Interpretation

This is a real positive pulse, but not live-grade yet.

Strengths:

- survives next-open execution;
- survives 10/5 bps stress;
- time distribution on the validated base universe is stable;
- not a single-symbol result: positive contribution from `LINK/SUI/LTC/DOT/ETH`.

Weaknesses:

- only `29` trades on the base universe;
- no trades in June/July in the current 360d window;
- symbol-OOS does not confirm portability (`PF 0.985`, net slightly negative).

## Decision

Do not put IVB1 long r003 on live money today.

Allowed next step:

- put r003 into shadow telemetry / risk `0.0`, or keep research-only and run one more preregistered gate.

Not allowed:

- no live risk >0 until either:
  1. symbol-selection hypothesis is preregistered and passes, or
  2. live shadow shows enough recent signals with acceptable simulated R.

## Portfolio implication

ATT1 r001 remains the only money-bearing crypto sleeve.

IVB1 long r003 becomes the top next crypto candidate because it addresses the missing bull-side sleeve, but it is not yet a deployable second sleeve.

