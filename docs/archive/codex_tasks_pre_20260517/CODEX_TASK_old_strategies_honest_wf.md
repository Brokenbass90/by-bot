# CODEX TASK: Honest walk-forward for legacy strategies

## Context
In March 2026, these strategies showed impressive in-sample numbers:
- `inplay_breakout` + `btc_eth_midterm_pullback` + `alt_sloped_channel_v1` → +89% (PF=2.12, 427 trades)

BUT: those were in-sample backtests — trained and tested on the same data.
The numbers were inflated by overfitting.

## Goal
Run an HONEST walk-forward validation to find out:
1. Do these strategies still work on out-of-sample data?
2. What is their real PF and return when they've never seen the test window?
3. Can any of them be added back to the live config?

## Walk-forward config

Use 22 rolling 45-day windows from 2025-04-13 to 2026-04-08 (identical to core2_honest_wf):

```
window_size_days: 45
step_days: 15
start: 2025-04-13
end: 2026-04-08
```

For EACH window: use DEFAULT params (no optimization). The goal is to measure
raw strategy quality, not to find a great parameter set (that would be overfitting again).

## Strategies to test

### Run A: inplay_breakout solo
```bash
backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT \
  --strategies inplay_breakout \
  --days 45 --tag {tag} \
  --risk_pct 0.01 --leverage 1 --fee_bps 6 --slippage_bps 2
```

### Run B: btc_eth_midterm_pullback solo
```bash
backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT \
  --strategies btc_eth_midterm_pullback \
  --days 45 --tag {tag} \
  --risk_pct 0.01 --leverage 1 --fee_bps 6 --slippage_bps 2
```

### Run C: alt_sloped_channel_v1 solo
```bash
backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ATOMUSDT,LTCUSDT,DOTUSDT \
  --strategies alt_sloped_channel_v1 \
  --days 45 --tag {tag} \
  --risk_pct 0.01 --leverage 1 --fee_bps 6 --slippage_bps 2
```

### Run D: all three combined (original stack)
```bash
backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ATOMUSDT,LTCUSDT,DOTUSDT,SUIUSDT,ADAUSDT,BCHUSDT \
  --strategies inplay_breakout,btc_eth_midterm_pullback,alt_sloped_channel_v1 \
  --days 45 --tag {tag} \
  --risk_pct 0.01 --leverage 1 --fee_bps 6 --slippage_bps 2
```

## Implementation

Use the same walk-forward runner as core2_honest_wf:
```bash
$PYTHON backtest/run_walkforward.py \
  --config configs/wf_old_strategies_honest_v1.json \
  --tag old_strategies_honest_wf_v1
```

Create `configs/autoresearch/old_strategies_honest_wf_v1.json` as a walk-forward spec
(no parameter grid — just run defaults across all windows).

## Decision criteria

After walk-forward completes, evaluate each strategy:

| Condition | Decision |
|---|---|
| Total PF > 1.20 AND trades > 40 | ✅ Add to live config |
| Total PF 1.10–1.20 AND trades > 40 | ⚠️ Add in reduced risk (risk_mult=0.5) |
| PF < 1.10 OR trades < 20 | ❌ Leave disabled |
| Max DD > 15% in any window | ❌ Leave disabled regardless |

## Output

Write results to `backtest_runs/old_strategies_honest_wf_v1/summary.csv` and
generate `backtest_runs/old_strategies_honest_wf_v1/verdict.md` with:
- Per-strategy pass/fail
- Recommended live config changes if any pass
- Comparison: original in-sample claim vs honest walk-forward result
