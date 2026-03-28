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

- Snapshot: [full_stack_baseline_20260325_reconstructed_v2.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/full_stack_baseline_20260325_reconstructed_v2.env)
- Run: [portfolio_20260328_122413_full_stack_baseline_20260325_reconstructed_v2_annual](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260328_122413_full_stack_baseline_20260325_reconstructed_v2_annual/summary.csv)
- Result: `+66.34%`, PF `1.508`, DD `5.1793`, `629` trades
- Notes:
  - best current deployable reconstruction of the historical winner
  - clearly better than the weaker transient live-mirror iterations
  - still under the historical anchor because breakout became too loose and
    overtraded

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

## Current Next Candidate

- Snapshot: [full_stack_baseline_20260325_reconstructed_v3_breakout_rebalanced.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/full_stack_baseline_20260325_reconstructed_v3_breakout_rebalanced.env)
- Purpose:
  - keep the successful `v2` reconstruction base
  - replace only the breakout execution shape with the stronger bounded
    `breakout_live_bridge_v3_density` frontier so breakout stops overtrading
