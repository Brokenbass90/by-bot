# Agent Sync

Last updated: 2026-03-29 09:00 UTC

Purpose:
- keep Claude and Codex aligned on what is real, what is live, and what is still only research
- reduce duplicated work and prevent accidental regressions from mixed context

## Source Of Truth

- Live crypto baseline:
  - [full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe.env)
  - live server already runs `v5`
- Historical research anchor:
  - [portfolio_20260325_172613_new_5strat_final](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260325_172613_new_5strat_final/summary.csv)
  - `+100.93%`, PF `2.078`, DD `3.6515`
- Current reproducible golden candidate:
  - [portfolio_20260328_225413_full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe_annual](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260328_225413_full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe_annual/summary.csv)
  - `+94.76%`, PF `2.141`, DD `2.8926`
- Journal:
  - [WORKLOG.md](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/WORKLOG.md)
- Roadmap:
  - [ROADMAP.md](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/ROADMAP.md)

## Current Live Stack

- `inplay_breakout`
- `btc_eth_midterm_pullback`
- `alt_sloped_channel_v1`
- `alt_resistance_fade_v1`
- `alt_inplay_breakdown_v1`

Disabled in live:
- `triple_screen_v132`
- `funding_rate_reversion_v1`
- `pump_fade_simple`
- `retest` families

## Ownership Split

Claude focus:
- autonomy infrastructure
- health gate wiring
- AI/operator architecture
- Claude-specific analyst tooling

Codex focus:
- strategy research
- portfolio compares
- live baseline integrity
- server rollout discipline
- journal / baseline truth maintenance

Shared rules:
- check [WORKLOG.md](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/WORKLOG.md) before major changes
- do not promote to live unless candidate beats `v5` on apples-to-apples compare
- do not describe a strategy as "implemented" unless smoke-run or backtest path is verified
- do not mix Alpaca monthly results with crypto portfolio baseline when discussing degradation

## Current Research Status

Running:
- `Elder v13 zoom`
  - [triple_screen_elder_v13_zoom.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/triple_screen_elder_v13_zoom.json)

Backtest-ready but not live-ready:
- `Funding Rate Reversion`
  - [funding_rate_reversion_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/funding_rate_reversion_v1.py)
  - [funding_rate_reversion_v1_grid.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/funding_rate_reversion_v1_grid.json)
  - [funding_rate_fetcher.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/funding_rate_fetcher.py)
  - smoke-run works; live funding data path into main bot still missing

Known weak / not promoted:
- `midterm_pullback_v2_btceth_v1` → `0 PASS`
- `pump_fade_simple_expanded_v1` → `0 PASS`
- `equities_monthly_v23_spy_regime_gate` → parser fixed, still `0 PASS`

## Immediate Next Steps

1. Finish `Elder v13` and judge whether it deserves a 6-strategy compare.
2. Launch full `funding_rate_reversion_v1` grid now that smoke-run is fixed.
3. Keep `Alpaca` on repair track, but do not confuse it with crypto baseline performance.
4. If Claude wires health gates into live, re-check against `v5` before any rollout.
