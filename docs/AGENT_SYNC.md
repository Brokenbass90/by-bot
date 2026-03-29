# Agent Sync

Last updated: 2026-03-29 15:45 UTC

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
- `Elder v14 recovery`
  - [triple_screen_elder_v14_recovery.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/triple_screen_elder_v14_recovery.json)
  - built because `v13` missed the real v12 PASS pocket (`BE=1.0`, `MAX_SIGNALS_PER_DAY=3`, `TIME_STOP=216/288`, `EXEC_MODE=eth/optimistic`, shorts enabled)
- `Funding Rate Reversion` full grid
  - [funding_rate_reversion_v1_grid.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/funding_rate_reversion_v1_grid.json)
- `Elder` as 6th strategy portfolio test
  - [portfolio_elder_6strat_test.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/portfolio_elder_6strat_test.json)
- `Alpaca v27` repair run
  - [equities_monthly_v27_intramonth_stop.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/equities_monthly_v27_intramonth_stop.json)
  - early frontier already produced PASS rows; best seen so far:
    - `net=69.80`
    - `PF=2.633`
    - `WR=56.3%`
    - `DD=10.74`
    - `negative_months=5`

Backtest-ready but not live-ready:
- `Funding Rate Reversion`
  - [funding_rate_reversion_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/funding_rate_reversion_v1.py)
  - [funding_rate_reversion_v1_grid.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/funding_rate_reversion_v1_grid.json)
  - [funding_rate_fetcher.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/funding_rate_fetcher.py)
  - smoke-run works; live funding data path into main bot still missing
- `Liquidation Cascade Entry`
  - [liquidation_cascade_entry_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/liquidation_cascade_entry_v1.py)
  - [liquidation_cascade_v1_grid.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/liquidation_cascade_v1_grid.json)
  - whitelist bug in `run_portfolio.py` fixed on 2026-03-29
  - direct smoke-run no longer crashes, but first 360d smoke produced `0` trades → not ready for full grid yet

Known weak / not promoted:
- `midterm_pullback_v2_btceth_v1` → `0 PASS`
- `pump_fade_simple_expanded_v1` → `0 PASS`
- `equities_monthly_v23_spy_regime_gate` → parser fixed, still `0 PASS`

## Claude Changes (session 19c/19d) — 2026-03-29

Done by Claude (do not revert without checking):
- `smart_pump_reversal_bot.py`: health_gate wired (6 strategy entry points) + allowlist_watcher started in `main()`
- `smart_pump_reversal_bot.py`: Telegram `tg_send()`/`tg_send_kb()`/`tg_trade()` chunking (3900 char max, numbered parts)
- `scripts/deepseek_weekly_cron.py`, `scripts/equity_curve_autopilot.py`: same chunking fix
- `strategies/liquidation_cascade_entry_v1.py`: new strategy (LONG after panic cascade) — registered in run_portfolio.py
- `configs/autoresearch/liquidation_cascade_v1_grid.json`: autoresearch spec ready (~3888 combos)
- `strategies/funding_rate_reversion_v1.py`: registered in run_portfolio.py (was unregistered)
- `scripts/funding_rate_fetcher.py`: live injector + historical downloader (Bybit API)
- `configs/autoresearch/funding_rate_reversion_v1_grid.json`: autoresearch spec ready (~2916 combos)
- `scripts/equities_monthly_research_sim.py`: added `--intramonth-portfolio-stop-pct` + `profit_factor` in summary.csv (was NaN)
- `configs/autoresearch/equities_monthly_v27_intramonth_stop.json`: 288-combo spec, relaxed neg_months=6

Do NOT re-add health gate checks — they are already in the bot.
Do NOT re-run equities v23 autoresearch — use v27 instead (v23 had wrong constraints).

## Claude Changes (session 19e) — 2026-03-29

Done by Claude (do not revert without checking):
- `bot/deepseek_research_gate.py`: NEW — 3-tier safety gate (AUTO/PROPOSAL/BLOCKED)
  - TIER 1 AUTO: pre-approved specs run immediately (7 builtins in `_BUILTIN_APPROVED`)
  - TIER 2 PROPOSAL: new specs write JSON to `configs/research_proposals/` + Telegram alert
  - TIER 3 BLOCKED: smart_pump_reversal_bot, credentials, baselines/, backup/
  - `check_triggers()`: fires WR<45% or PAUSE/KILL equity curve → auto-proposes spec
  - `update_kill_zones()`: flags symbols PnL < -0.5$/30d for human review
  - `status_report()`: for /research_status Telegram command
  - Singleton: `gate = ResearchGate()`
- `scripts/deepseek_weekly_cron.py`: gate wired in 3 places:
  - Import: `from bot.deepseek_research_gate import gate as _research_gate` (with try/except)
  - Phase 0 (before audit): gate status check, pending proposal count
  - After audit: `gate.check_triggers(strat_stats)` → WR proxy from PF, proposals fired if triggered
  - Report phase: gate_status_text appended, pending proposals shown in footer with IDs
- `bot/family_profiles.py`: NEW — per-symbol-family parameter multipliers (syntax verified OK)
- `configs/family_profiles.json`: NEW — hot-reloadable multiplier definitions (3 families)

Do NOT re-add gate import to deepseek_weekly_cron.py — already there.
Do NOT remove gate status block from report — it shows pending proposals to Telegram.

## Immediate Next Steps

1. **SR Break Retest — resume** (run on local machine, was at 449/12288):
   ```
   nohup python3 scripts/run_strategy_autoresearch.py \
     --spec configs/autoresearch/sr_break_retest_volume_v1_revival_v1.json \
     > /tmp/sr_revival.log 2>&1 &
   ```
2. Run on server (all can run in parallel):
   ```
   python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/equities_monthly_v27_intramonth_stop.json
   python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/funding_rate_reversion_v1_grid.json
   python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/liquidation_cascade_v1_grid.json
   ```
3. Finish `Elder v13` → run `configs/autoresearch/triple_screen_elder_v13_zoom.json`
4. **Bot restart on server** to activate health_gate + allowlist_watcher (code is in bot, restart needed):
   ```
   systemctl restart bybit-bot   # or: pkill -f smart_pump_reversal_bot && nohup python3 smart_pump_reversal_bot.py &
   ```
5. **Family profiles** — integrate `profiles.scale()` calls into live strategies once backtests confirm gain
6. **Regime allocator / cross-strategy correlation layer** — not started yet

## Server Reality Check — 2026-03-29

- `bybot.service` is `active`
- weekly crons confirmed on server:
  - `dynamic_allowlist_weekly`
  - `deepseek_weekly_cron`
- current live env still reflects `v5` core:
  - `ASC1_SYMBOL_ALLOWLIST=ADAUSDT,LINKUSDT,ATOMUSDT`
  - `ARF1_SYMBOL_ALLOWLIST=ADAUSDT,SUIUSDT,LINKUSDT,DOTUSDT,LTCUSDT`
  - `BREAKDOWN_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT`
  - `BREAKOUT_QUALITY_MIN_SCORE=0.53`
  - `ENABLE_TS132_TRADING=0`
