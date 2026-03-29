# Golden Portfolio Baselines

This file keeps the portfolio baselines we should compare against before changing
live crypto deployment. The point is simple: stop drifting from strong stacks
without noticing it, and only promote a new stack when it clears the current
golden reference on an apples-to-apples annual run.

## Historical Research Anchor

- Tag: `new_5strat_final`
- Run: [portfolio_20260325_172613_new_5strat_final](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260325_172613_new_5strat_final/summary.csv)
- Result: `+100.93%`, PF `2.078`, DD `3.6515`, `446` trades
- Notes:
  - strongest known research result for the 10-symbol, 5-sleeve crypto stack
  - not yet a clean one-file deploy snapshot, so it is the research anchor, not
    an automatic live rollback target

## Current Reproducible Golden Candidate

- Snapshot: [full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe.env)
- Historical-window run: [portfolio_20260328_225413_full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe_annual](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260328_225413_full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe_annual/summary.csv)
- Recent-window run: [portfolio_20260328_233022_full_stack_baseline_20260328_v5_dynamic_allowlist_recent_annual](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260328_233022_full_stack_baseline_20260328_v5_dynamic_allowlist_recent_annual/summary.csv)
- Result:
  - historical window: `+94.76%`, PF `2.141`, DD `2.8926`, `420` trades
  - recent window: `+89.65%`, PF `2.121`, DD `2.8821`, `427` trades
- Notes:
  - strongest fully reproducible stack we currently have
  - validated on both the older anchor-like window and a fresher window
  - already promoted to live as the current full-stack overlay

## Promotion Rules

- Do not change live crypto deployment unless the candidate stack is compared on
  a matching annual window and symbol union.
- Prefer promoting a stack only when it improves the current reproducible
  golden candidate on at least one of:
  - materially higher net return with acceptable DD
  - materially better PF with similar net
  - materially lower DD with similar net
- Treat regressions in both net return and PF as a rejection, even if a single
  sleeve looks better in isolation.
- Keep both references:
  - the historical research anchor
  - the current reproducible golden candidate

## Current Improvement Frontier

- `v5` is the operational baseline.
- New candidates should now beat `v5`, not `v2` or `v3`.
- Current open research fronts:
  - `Elder/TS132` zoom and 6-strategy portfolio validation
  - `Funding Rate Reversion` as a new Bybit-specific sleeve
  - dynamic family profiles / health-gated autonomy
  - Alpaca monthly smoothness repair
