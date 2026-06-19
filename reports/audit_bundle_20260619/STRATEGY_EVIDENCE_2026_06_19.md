# Strategy Evidence Packet - 2026-06-19

## Scope and data boundary

- Live source: `live_trade_events.jsonl`, 112 events, 40 closed trades.
- Live period actually available: 2026-04-05 through 2026-06-18. A 6-12 month live/shadow journal does not exist in the repository or on the server.
- Long-horizon evidence therefore comes from deterministic backtests, not fabricated live history.
- Server snapshot at 2026-06-19: bot alive, `bear_chop`, feed advancing, no open positions, no allocator hard block.

## Current live package

Runtime heartbeat reports:

| Sleeve | Human name | Mode | Risk multiplier |
|---|---|---:|---:|
| `flat` | short from resistance | live | 0.30 |
| `range` | range-boundary retest | live, short-only | 0.25 |
| `att1` | trendline touch | shadow | 0.00 |
| `bounce1` | support bounce | shadow | 0.00 |
| `breakdown` | support breakdown/retest | shadow | 0.00 |
| `ivb1` | impulse/volume breakout | shadow | 0.00 |
| `midterm` | BTC/ETH medium-term pullback | shadow | 0.00 |
| `elder` | Elder triple screen | disabled | 0.05 configured but not enabled |

`.env` contains `FLAT_RISK_MULT=0.10`, while the live heartbeat reports 0.30. This is an overlay/runtime-state discrepancy; the heartbeat is the effective process state used for the table above.

## Live closed-trade evidence

| Strategy | Trades | Net PnL, USDT | PF | Win rate | t-stat |
|---|---:|---:|---:|---:|---:|
| Entire journal | 40 | -3.8081 | 0.517 | 32.5% | -1.729 |
| Breakdown short | 15 | -2.4170 | 0.289 | 26.7% | -2.170 |
| Current Range | 15 | -1.1768 | 0.624 | 33.3% | -0.731 |
| Trendline touch | 7 | -1.2827 | 0.056 | 14.3% | -2.702 |
| Flat resistance short | 2 | +0.3234 | n/a | 100% | sample too small |

Current Range directional split:

| Side | Trades | Net PnL, USDT | PF | Win rate |
|---|---:|---:|---:|---:|
| Long | 12 | -1.7069 | 0.425 | 25.0% |
| Short | 3 | +0.5301 | 4.364 | 66.7% |

Three short trades are not statistical proof. The 360-day live-parity sweep below is the stronger evidence.

## Completed and interrupted research

### Current live Range implementation

- Code path: `smart_pump_reversal_bot.py -> RangeStrategy`.
- Sweep: `range_live_side_exit_repair_v1`, 216 combinations, 162 with trades.
- PASS: 0.
- Best PF: r078, 157 trades, net +0.66, PF 1.027, DD 5.35%.
- Best score: r093, 166 trades, net -0.02, PF 0.999, DD 4.74%.
- Result: the current live Range is approximately break-even at best after the configured costs, not a demonstrated annual edge.

### ARS1 Bollinger/RSI range scalp (different strategy)

- Code path: `strategies/alt_range_scalp_v1.py`.
- It is not the `RangeStrategy` currently entering live orders.
- The interrupted annual sweep completed eight configurations before being stopped to avoid a 15,552-cell brute-force overfit.
- r003: 105 trades, net +11.50%, PF 1.483, DD 5.98%.
- r004: 109 trades, net +13.95%, PF 1.565, DD 6.83%.
- Both numbers used the legacy signal-price execution and must be rerun with next-open execution before shadow promotion.

Directional and chronological decomposition:

| Candidate | Segment | Trades | Net | PF | t-stat |
|---|---|---:|---:|---:|---:|
| r003 | Long | 61 | +4.59 | 1.308 | 0.678 |
| r003 | Short | 44 | +6.91 | 1.773 | 1.465 |
| r003 | First 70% | 73 | -0.21 | 0.988 | -0.038 |
| r003 | Last 30% | 32 | +11.70 | 2.838 | 1.958 |
| r004 | Long | 64 | +7.28 | 1.469 | 0.968 |
| r004 | Short | 45 | +6.67 | 1.726 | 1.408 |
| r004 | First 70% | 76 | -1.14 | 0.938 | -0.208 |
| r004 | Last 30% | 33 | +15.09 | 3.389 | 2.264 |

The positive result is concentrated in the latest 30% of the sample. It is a useful shadow candidate, not yet a live allocation.

### Elder Triple Screen

- 541 completed parameter combinations, PASS 0.
- PF range: 0.573-0.838.
- Best observed: 2,876 trades, net -70.10%, PF 0.838, DD 72.18%.
- The duplicate local run was stopped; local compute moved to VWAP.
- This is a structural strategy failure under the tested adapter, not a parameter-neighborhood miss.

### InPlay Retest v3

- Two pre-fix server combinations: 1,050-1,077 trades, PF 0.511-0.517, DD 78-79%.
- These runs mixed structure-TF ATR with entry-TF retest geometry and evaluated the caller's 5m bar despite `IRV3_ENTRY_TF=15`.
- They are retained as failure evidence but are invalid for evaluating the corrected implementation.
- Corrected implementation now:
  - requires `row_start + timeframe <= signal_time`;
  - uses the latest fully closed entry-TF bar as the trigger;
  - uses entry-TF ATR for retest/touch/pierce/entry-distance;
  - keeps structure-TF ATR for level clustering and level-based stop/TP offsets;
  - uses timestamp-based cooldown.

### Pump Fade and Breakdown

- Their bounded queues are running after the invalid InPlay sweep was stopped.
- Promotion specifications now require next-open execution.
- Historical live evidence for Breakdown is negative: 15 short trades, PF 0.289, net -2.417 USDT.

## Execution and cost model

Before this session:

- Entry: strategy signal price, usually the close of the signal bar.
- Fee: `fee_bps` applied on entry and exit.
- Slippage: `slippage_bps` applied adversely on entry and exit.
- Typical research setting `fee_bps=6`, `slippage_bps=2` means 16 bps round-trip drag, not 8 bps.
- Breakdown research uses 10 bps fee plus 10 bps slippage per side: 40 bps round-trip drag.
- Historical funding can be exposed to strategies through `fetch_funding_rate`, but the generic engine does not debit periodic funding cashflows from PnL.

After this session:

- `BacktestParams.entry_on_next_open` is implemented in single-symbol and portfolio engines.
- `--entry-on-next-open` is available in `run_portfolio.py` and `run_month.py`.
- Promotion specs for InPlay, Elder, Pump Fade, Breakdown, and ARS1 require it.
- The next-open position is processed against the same bar's OHLC; if TP and SL are both reachable, SL wins.
- Invalid signals are now actually rejected by the portfolio engine. Previously `validate()` was called but its `False` return value was ignored.
- The single-symbol engine now records positions fully closed by TP; previously such trades could disappear from `run_month` output.
- New summaries record `entry_execution`, `fee_bps_per_side`, and `slippage_bps_per_side`.

## Level geometry look-ahead audit

- `find_pivots` requires right-side bars to confirm a pivot. This is not future leakage when all supplied rows are already closed before the signal; it is delayed confirmation.
- `cluster_horizontal_levels` and `regression_channel` consume only supplied rows.
- InPlay now filters structure and entry rows by close time before calling these functions.
- Tests prove future/forming bars are ignored.

## Risk facts

- Current crypto equity is approximately 121 USDT.
- User-defined live-canary daily loss limit: 1%, approximately 1.21 USDT at current equity.
- Reserve capital: 2,500 USD, not deployed until sleeves pass promotion gates.
- Runtime base risk is 1%; current orchestrator and allocator multipliers reduce effective displayed risk per trade to approximately 0.44% before sleeve multipliers.
- The allocator can size or block validated sleeves; it cannot turn a non-positive strategy into a positive one.

## Files in this packet

- `live_trade_events.jsonl`: complete available server journal.
- `server_results/range_live_results.csv`: current live Range sweep.
- `server_results/range_live_ranked_results.csv`: current live Range ranking.
- `server_results/elder_results_partial.csv`: 541 completed Elder variants.
- `server_results/inplay_v3_results_partial.csv`: two invalidated pre-fix InPlay variants.
- `server_results/range_ars1_results_partial.csv`: first eight ARS1 variants.
- `range_ars1_r003/` and `range_ars1_r004/`: trades and summaries for the two initial ARS1 candidates.

## Active validation sequence

1. Re-run ARS1 r003/r004 with next-open execution and identical costs; split long/short and chronological 70/30.
2. Run a bounded corrected InPlay v3 diagnostic before any grid expansion.
3. Let Pump Fade, Breakdown, and local VWAP complete bounded diagnostics.
4. Keep Elder disabled pending a logic redesign; do not continue its 52,488-cell grid.
5. Only candidates surviving next-open, OOS/monthly, and live-stack comparison enter shadow, then tiny canary.
