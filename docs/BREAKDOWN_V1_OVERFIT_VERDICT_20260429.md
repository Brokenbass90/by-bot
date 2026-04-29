# Breakdown v1 Overfit Verdict — 2026-04-29

## Question

Claude's `breakdown_v1_recent180_focus_v1` winner looked strong on recent 180d:

- PF `1.833`
- DD `8.69%`
- trades `126`
- net `+21.73`

But Codex additivity replay against `crypto_income_live_canary_v2` showed:

- `breakdown_v1` attribution `-9.32`
- trades `346`
- full package return dropped from `+45.44%` to `+30.16%`
- DD rose from `5.95%` to `9.73%`
- red months rose from `1` to `4`

The task was to decide whether this is a control-plane regression or a recent-window overfit.

## Runs

### Standalone 330d, RSI_MAX=50

Command log:

- `logs/claude_breakdown_330d_overfit_20260429.log`

Run dir:

- `backtest_runs/portfolio_20260429_103102_claude_breakdown_330d_overfit_check_rsi50_20260429`

Result:

- return `+6.26%`
- PF `1.114`
- WR `54.1%`
- DD `9.826%`
- trades `244`

Symbol attribution:

| Symbol | PnL | Trades | WR |
|---|---:|---:|---:|
| ADAUSDT | `+3.69` | `62` | `56.5%` |
| LINKUSDT | `+3.39` | `56` | `57.1%` |
| ETHUSDT | `-0.09` | `55` | `54.5%` |
| BTCUSDT | `-0.30` | `20` | `50.0%` |
| SOLUSDT | `-0.44` | `51` | `49.0%` |

### Standalone 330d, RSI_MAX=55

Run dir:

- `backtest_runs/portfolio_20260429_103146_claude_breakdown_330d_overfit_check_rsi55_20260429`

Result was identical to RSI=50:

- return `+6.26%`
- PF `1.114`
- WR `54.1%`
- DD `9.826%`
- trades `244`

This means the `RSI_MAX=50` vs `55` mismatch in notes does not change this window.

### WF-22, winner params

Command log:

- `logs/claude_breakdown_wf22_overfit_20260429.log`

Parameters:

- `BREAKDOWN_LOOKBACK_H=36`
- `BREAKDOWN_MIN_BREAK_ATR=0.2`
- `BREAKDOWN_RR=1.6`
- `BREAKDOWN_RSI_MAX=50`
- `BREAKDOWN_SL_ATR=2.2`
- `BREAKDOWN_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT`
- `BREAKDOWN_ALLOW_LONGS=0`
- `BREAKDOWN_ALLOW_SHORTS=1`

WF summary:

- windows `22`
- window size `45d`
- AvgPF `1.099`
- PF > 1.00: `10/22`
- PF > 1.15: `9/22`
- average trades/window `52`
- runner verdict: `WEAK — do not deploy`

Worst early cluster:

| Window End | PF | Trades | Net |
|---|---:|---:|---:|
| 2025-05-15 | `0.521` | `46` | `-5.13%` |
| 2025-05-30 | `0.142` | `47` | `-9.66%` |
| 2025-06-14 | `0.538` | `53` | `-5.23%` |
| 2025-06-29 | `0.703` | `62` | `-4.06%` |

Best recent cluster:

| Window End | PF | Trades | Net |
|---|---:|---:|---:|
| 2026-02-09 | `1.908` | `53` | `+8.10%` |
| 2026-02-24 | `1.660` | `70` | `+7.66%` |
| 2026-03-11 | `3.023` | `57` | `+12.30%` |
| 2026-03-26 | `1.541` | `48` | `+2.83%` |

## Verdict

`breakdown_v1_recent180_focus_v1` is not a clean control-plane casualty. It is mostly a recent-window winner that weakens badly on the longer window and fails WF-22.

Do not deploy `breakdown_v1` into live canary now.

Next step is not to patch allocator blindly. The correct route is a new breakdown/breakout research pass with WF acceptance built into the search:

- split by regime: `bear_trend` vs `bear_chop`
- compare `breakdown_v1` with `inplay_breakout` as a paired directional sleeve
- reject parameter sets that win only in the latest 90-180d cluster
- only revisit live additivity if standalone annual PF >= `1.5`, DD <= `8%`, trades >= `70`, and WF pass >= `13/22`
