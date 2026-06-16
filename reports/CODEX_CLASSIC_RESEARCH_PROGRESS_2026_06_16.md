# Codex Classic Research Progress — 2026-06-16

## Operator truth

- Live crypto bot is active on server; no live restart was performed in this pass.
- Current Alpaca order-driving cron is still `alpaca_v38_hybrid_top4_candidate.env` on `$500`.
- `alpaca_adaptive_v1` existed as research code and was the best 2022 bear protection variant, but it was not order-driving in server cron before this pass.
- To avoid two managers fighting on one Alpaca paper account, `alpaca_adaptive_v1` is now running as **shadow_no_orders** on `$1000`.

## New tooling deployed

- `scripts/classic_research_report.py`
  - reads a portfolio run or autoresearch dir
  - writes monthly tables, bear-month verdict, and simple stack comparison
- `scripts/run_classic_research_queue.py`
  - sequential classic-strategy queue
  - after each spec, writes `reports/CLASSIC_RESEARCH_<name>_<stamp>.md/json`
- `scripts/alpaca_adaptive_shadow.py`
  - no orders
  - writes `runtime/alpaca_adaptive_v1_shadow_latest.{json,md}`
- `backtest/monthly_analysis.py`
  - supports explicit bear-month verdicts for trade streams that do not carry regime labels

## Verification

- Local full tests: `307 passed`
- Server targeted tests for monthly/stack/classic report: `11 passed`
- Commit pushed: `af2550d Add classic research reporting and adaptive shadow`

## Server runs

### Inplay breakout/retest runner

Completed report:

- `reports/CLASSIC_RESEARCH_inplay_breakout_retest_runner_current_v1.md`
- Best ranked candidate: `inplay_breakout_retest_runner_current_v1_r002`
- Metrics: `31` trades, net `-5.16`, PF `0.237`, WR `0.258`, DD `5.2540`
- Monthly verdict: `FAIL`
- Red bear months: `2026-03`, `2026-04`
- Stack verdict: `neutral`, no trades dropped by the simple slot check

Interpretation: the current inplay breakout implementation/params are not the trader-like WLD setup the operator wants. It should not be promoted. The next inplay focus is first-touch bounce/retest logic, not this failed runner.

### IVB1

Still running under `breakout_runner_day_20260616`.

Early rows:

- PF range roughly `2.18..2.95`
- DD around `0.59`
- Fails current gate because trades `<72` and net `<8.0`

Interpretation: quality may exist, frequency is too low. This is a candidate for controlled relaxation/frequency work, not a live risk increase yet.

### Classic queue

Running in screen:

- `classic_research_queue_20260616`

Queue order:

1. `range_scalp_v1_annual_focus_v2`
2. `package_elder_modes_exact_probe_v1`
3. `package_sc1_modes_exact_probe_v1`
4. `package_asb1_slope_break_v1`
5. `pump_fade_v5_bear_window_v1`
6. `breakdown_v1_current90_focus_v1`
7. `inplay_first_touch_bounce_v1`

Log:

- `logs/classic_research_queue_20260616.log`

Main queue report will appear as:

- `reports/CLASSIC_RESEARCH_QUEUE_<stamp>.md`

### Alpaca adaptive shadow

Current shadow snapshot:

- `runtime/alpaca_adaptive_v1_shadow_latest.md`

First snapshot at `$1000`:

- regime: `ok`
- picks: `UNH`, `LLY`, `AAPL`, `JPM`
- native trailing min capital for all current picks: `$8567.72`

Interpretation: `$1000` still produces fractional quantities for this basket, so Alpaca native trailing is not available. Protection must remain software trail + broker stop unless using a larger account or excluding high-price names like `LLY`.

Cron added:

```cron
10 13 * * 1-5 /bin/bash -lc 'cd /root/by-bot && .venv/bin/python scripts/alpaca_adaptive_shadow.py --capital 1000 --target-alloc-pct 70 --max-positions 4 >> logs/alpaca_adaptive_shadow.log 2>&1' # alpaca_adaptive_shadow_codex
```

## Next checkpoint

Return after either:

- `2-3h` for the first queue result (`range_scalp`) and IVB1 progress, or
- evening / after US market close for Alpaca v38 + adaptive shadow comparison and more classic queue output.

## Decision rule

- Do not raise directional live risk just because the bot is quiet.
- If stack comparison shows a naked strategy is good but the stack blocks it, relax the specific blocker.
- If the naked strategy is negative, do not blame the stack; repair entry/levels/exits or retire that variant.
