# Agent Sync

Last updated: 2026-04-08 13:05 UTC

## 2026-04-08 refresh note

The older sections below still contain useful history, but do not treat them as a full live-state description anymore.

Current live foundation truth now also includes:
- `bybot.service` is the real systemd service on server
- live heartbeat exists:
  - `/root/by-bot/runtime/bot_heartbeat.json`
- external watchdogs exist:
  - heartbeat watchdog cron
  - control-plane freshness check cron
  - control-plane repair watchdog cron
- deterministic geometry exists and runs hourly on server:
  - `/root/by-bot/runtime/geometry/geometry_state.json`
- compact operator truth pack exists and runs hourly on server:
  - `/root/by-bot/runtime/operator/operator_snapshot.json`
  - `/root/by-bot/runtime/operator/operator_snapshot.txt`
- live operator snapshot now also includes:
  - current `strategy_health` summary
  - historical health timeline metadata
- live router code now includes deterministic geometry-aware symbol scoring / filtering
- live allocator code now includes portfolio overlap / exposure haircuts
- live regime builder now includes a weak bull-trend softener:
  - `flat` can be re-enabled when bull-trend confidence is only modest
- `alt_support_bounce_v1` regime logic now respects its configured gap threshold:
  - old hard-coded `gap_pct <= 1.0` was removed
  - support-bounce research should no longer be judged off a partially false regime gate
- local/offline control-plane replay now also has historical health context:
  - `runtime/control_plane/strategy_health_timeline.json`
  - replay no longer has to reuse one current `configs/strategy_health.json` across the whole year
- foundation one-liners now work with default SSH key discovery:
  - `scripts/deploy_foundation.sh`
  - `scripts/server_status.sh`
- live control-plane state was manually rebuilt after the latest deploy:
  - regime
  - router
  - allocator
  - geometry
  - operator snapshot
- current live allocator outcome at last direct check:
  - `regime=bull_trend`
  - `breakdown=False`
  - `flat=True`
  - `midterm=False`
  - allocator status still `degraded`, but now for health/risk reasons, not because the old flat hard-disable path survived
- live server now also has the explicit promotion artifacts:
  - `configs/crypto_promotion_policy.json`
  - `scripts/evaluate_crypto_promotion.py`
- duplicate control-plane health cron was removed; the live server now keeps one:
  - `# bybot_cp_health`
- active local research frontier now includes:
  - `core3_range_additivity_recent180_v2`
  - `core3_range_additivity_annual_v1`
  - `support_bounce_v1_regime_gap_repair_v1`
  - `impulse_volume_breakout_v1_annual_repair_v1`

When in doubt, prefer:
- [docs/ROADMAP.md](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/ROADMAP.md)
- [docs/JOURNAL.md](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/JOURNAL.md)
- [docs/WORKLOG.md](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/WORKLOG.md)
over stale assumptions in older handoff notes.

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
- `Elder v15 short-bias`
  - [triple_screen_elder_v15_short_bias.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/triple_screen_elder_v15_short_bias.json)
  - this is the only research branch we are intentionally keeping alive right now
  - purpose: verify whether the short-only / tighter-exit Elder branch can hold `4` negative months instead of `5-6`
- `Elder v16 short-density`
  - [triple_screen_elder_v16_short_density.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/triple_screen_elder_v16_short_density.json)
  - launched once `v15` lost momentum; purpose is to recover density/net on top of the smoother short-only shape
- `micro_scalper_v2 weak-chop density`
  - [micro_scalper_v2_weak_chop_density.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/micro_scalper_v2_weak_chop_density.json)
  - next candidate for monetizing the quiet `impulse_weak / tradable_impulse` regime where the core live stack often sits idle
- `Alpaca v30 regime concentration proxy`
  - [equities_monthly_v30_regime_concentration_proxy.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/equities_monthly_v30_regime_concentration_proxy.json)
  - next real Alpaca repair step after `v29`; approximates dynamic concentration using benchmark/breadth/correlation controls

Prepared next, but not launched yet:
- `Elder v17 structural repair`
  - [triple_screen_elder_v17_structural_repair.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/triple_screen_elder_v17_structural_repair.json)
  - code-level repair path over [triple_screen_v132.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/archive/strategies_retired/triple_screen_v132.py)
  - smoke-tested only; not promoted to a full grid because the first strict canonical run came back too dry/negative

Finished / superseded / not worth more heat right now:
- `Elder v13 zoom` — superseded
- `Elder v14 recovery` — useful diagnosis, but superseded by `v15`
- `portfolio_elder_6strat_test` — premature before Elder itself is fixed
- `breakout_weak_chop_probe_v1` — isolated idea looked fine, but full-stack compare lost to `v5`
- `liquidation_cascade_v1_grid` — integration/logical density still too weak

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
- `breakout weak-chop overlay` → loses badly to `v5` at full-stack level
- `Elder v17 strict canonical smoke` → syntactically healthy, strategically too dry (`13 trades`, `net=-0.56`, `PF=0.708`)

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

## Claude Changes (session 19f) — 2026-03-29

### Bugs fixed:

**`strategies/liquidation_cascade_entry_v1.py`** — TradeSignal constructor was broken:
- Was: `TradeSignal()` no-arg → TypeError; then `TradeSignal(direction=...)` → also fails (wrong kwarg + missing `symbol`)
- Fix: `from .signals import TradeSignal` (same as FR Reversion) + correct args: `symbol` from `store.symbol`, `side=direction`, `be_trigger_rr` instead of absolute `be_trigger`
- This caused CalledProcessError in LC autoresearch (0-trade run → empty summary → runner crash)

**`configs/autoresearch/funding_rate_reversion_v1_grid_v2.json`** (NEW) — FR grid v2:
- v1 bug: `FR_LATEST=0.0008` ≤ both tested thresholds → FR filter always-on → tested RSI+EMA only → max PF 1.21, 0/2916 passed
- v2: `FR_LATEST=+0.003` (extreme positive), threshold=[0.001, 0.002] → filter fires selectively for shorts
- Shorts-only pass, relaxed constraints PF≥1.4, 972 combos, ~15 min

### Run commands (restart on your machine):
```bash
# LC grid — restart from scratch (old run was broken, safe to overwrite)
nohup python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/liquidation_cascade_v1_grid.json > /tmp/lc_v1.log 2>&1 &

# FR Reversion v2 — new shorts-only pass
nohup python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/funding_rate_reversion_v1_grid_v2.json > /tmp/fr_v2_shorts.log 2>&1 &
```

## Immediate Next Steps

1. **Finish `Elder v15` first.** Do not start a new heavy queue while it is still the only branch with a live diagnosis value.
2. **If `v15` holds `4` negative months**, launch [triple_screen_elder_v16_short_density.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/triple_screen_elder_v16_short_density.json) next.
3. **If `v15` falls back to `5-6` negative months**, freeze Elder as research-only and move the next strategy cycle to Funding / Alpaca instead of burning more time on it.
4. **Autonomy bundle reality check** — do **not** assume server restart enables `health_gate + allowlist_watcher`. Those files exist locally, but were not yet deployed to `/root/by-bot`; current server restart only restarts the existing `v5` bot.
5. **Family profiles** — integrate `profiles.scale()` calls into live strategies only after backtests show gain.
6. **Regime allocator / cross-strategy correlation layer** — not started yet.

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
- autonomy files are **not** on the server yet:
  - `bot/allowlist_watcher.py`
  - `bot/health_gate.py`
  - `bot/deepseek_research_gate.py`
- related scripts also not confirmed on server:
  - `scripts/equity_curve_autopilot.py`
  - `bot/family_profiles.py`
- therefore a simple bot restart does **not** activate those features yet

## Autonomy Reality Check — 2026-03-29

- locally, [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) already imports and uses:
  - `bot.health_gate`
  - `bot.allowlist_watcher`
- locally, [scripts/deepseek_weekly_cron.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/deepseek_weekly_cron.py) already imports:
  - `bot.deepseek_research_gate`
- local syntax check passed for:
  - `smart_pump_reversal_bot.py`
  - `scripts/deepseek_weekly_cron.py`
  - `bot/allowlist_watcher.py`
  - `bot/health_gate.py`
  - `bot/deepseek_research_gate.py`
  - `bot/family_profiles.py`
  - `scripts/equity_curve_autopilot.py`
- `family_profiles` is only partially integrated right now:
  - active in `strategies/alt_sloped_channel_v1.py`
  - active in `strategies/micro_scalper_v1.py`
  - not yet wired into the rest of the live core sleeves

## Codex Changes (session 27d) — 2026-04-08

### Foundation truth updated:

- There is now a true stitched system harness:
  - [scripts/run_dynamic_crypto_annual.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_dynamic_crypto_annual.py)
- This is the new honest path for “is the rebuilt dynamic system actually better?” because it:
  - rebuilds historical regime
  - rebuilds historical router baskets
  - selects historical strategy health snapshot
  - applies allocator enable/risk outcome
  - runs actual portfolio backtests window by window with carried equity
- [backtest/run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py) now respects live-style sleeve risk envs when `ALLOCATOR_ENABLE=1`, so stitched tests can use per-sleeve allocator multipliers instead of the old breakout/midterm-only shim.

### First stitched result:

- [dynamic_system_smoke90_v4 summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_133617_dynamic_system_smoke90_v4/summary.json)
  - `+11.54%`
  - PF `2.2167`
  - WR `58.89%`
  - DD `1.8463%`
  - `0` negative months
- Windows:
  - w01 `bear_chop` → `breakdown + flat + sloped` → `+9.40`, PF `2.515`
  - w02 `bear_chop` → `flat + sloped` → `-0.15`, PF `0.939`
  - w03 `bear_chop` → `breakdown + flat` → `+2.29`, PF `3.712`

### Important implementation notes:

- The harness already caught and fixed two honesty bugs:
  - router/allocator handoff lost symbol baskets
  - `run_portfolio` could still drift into live fetch instead of pure cached replay
- The harness now forces `BACKTEST_CACHE_ONLY=1` for reproducible stitched tests.

### Immediate next step:

- launch and read a full `360d` stitched dynamic run
- compare:
  - stitched dynamic system
  - static legacy package
  - control-plane replay only
- only after that reopen promotion discussion for new sleeves

## Codex Changes (session 27e) — 2026-04-08

### Full annual stitched truth:

- [dynamic_system_annual_v1 summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_133825_dynamic_system_annual_v1/summary.json)
  - `+2.97%`
  - PF `1.0636`
  - WR `46.89%`
  - DD `8.6842%`
  - `6` negative months
- [dynamic_windows.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_133825_dynamic_system_annual_v1/dynamic_windows.csv)
  - most windows stayed in applied `bull_chop`
  - active sleeves were mainly `breakout`, `sloped`, `flat`
  - the new foundation is honest enough to expose weak months instead of smoothing them away

### What is running now:

- `core2_honest_wf_360d_20260408`
- `ivb1_ema_wf_360d_20260408`
- `ivb1_off_wf_360d_20260408`
- `pump_fade_v4r_bear_window`

### Important truth:

- `CODEX_TASK_next_steps.md` is directionally useful, but stale on IVB1 implementation:
  - `IVB1_REGIME_MODE` already exists in [strategies/impulse_volume_breakout_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/impulse_volume_breakout_v1.py)
  - the real next step is not “add the flag”, but long-horizon `off vs ema` comparison with the repaired base
- Do not call IVB1 live-ready until:
  - `ema` vs `off` walk-forward is complete
  - stitched annual system truth is acceptable
  - portfolio compare is not worse than the honest core2 backbone
