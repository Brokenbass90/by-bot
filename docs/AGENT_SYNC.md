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

### Additional 27e truth:

- [pump_fade_v4r_bear_window results.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260408_141723_pump_fade_v4r_bear_window/results.csv)
  - finished `81/81`
  - every row failed
  - best row still `net=-0.27`, `PF=0.000`
  - verdict: do not treat `pump_fade_v4r` as an active bear-window answer
- `core2_honest_wf_360d_20260408` needed a cache-only restart because the first attempt wandered into a stuck network-backed portfolio subprocess; the honest backbone run is now `core2_honest_wf_360d_cache_20260408`

## Codex Changes (session 27f) — 2026-04-08

### Live repair / foundation truth:

- `IVB1` is now wired into live code and policy:
  - [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py)
  - [configs/portfolio_allocator_policy.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/portfolio_allocator_policy.json)
- `WATCHDOG_AUTO_RESTART` is no longer a dead env var under cron:
  - [scripts/bot_health_watchdog.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/bot_health_watchdog.sh)
  - [scripts/check_control_plane_health.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/check_control_plane_health.sh)
  - both now source live `.env`
- `MIN_NOTIONAL_USD` is now env-driven with live patch support:
  - [scripts/apply_live_control_plane_env_patch.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/apply_live_control_plane_env_patch.py)
  - current live `.env` was patched to `MIN_NOTIONAL_USD=5.0`
- foundation deploy is now robust against first-start failure and uploads the IVB1 module:
  - [scripts/deploy_foundation.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/deploy_foundation.sh)

### Current live server truth:

- `bybot.service` is back to `RUNNING`
- heartbeat is fresh again
- control-plane files are fresh
- `impulse` sleeve now exists in allocator state, but stays disabled because:
  - `symbol_count=0`
  - `degraded_mode`
- live status line currently shows only `flat=True`; this is honest, not a wiring bug

### Honest validation truth:

- `pump_fade_v4r_bear_window`
  - final verdict still `81/81 fail`
- `ivb1_ema_wf_360d_20260408`
  - cumulative `net=-0.93`
  - positive windows `7/23`
- `ivb1_off_wf_360d_20260408`
  - cumulative `net=+13.78`
  - positive windows `18/23`
- `core2_honest_wf_360d_cache_20260408`
  - cumulative `net=+12.79`
  - positive windows `11/23`

### Immediate implication:

- The next good strategy step is **not** to promote IVB1 blindly.
- The next good step is:
  - treat `IVB1 off` as the better candidate than `IVB1 ema`
  - keep `pump_fade` out of focus
  - compare `core2` vs `core2 + IVB1 off` under honest annual / portfolio criteria

## Codex Changes (session 27g) — 2026-04-08

### Important truth correction:

- The old stitched annual `dynamic_system_annual_v1` was not yet testing the intended modern stack.
- It still routed:
  - `inplay_breakout`
  - `alt_sloped_channel_v1`
  - `alt_resistance_fade_v1`
  because `breakout` had historically survived in the policy and `IVB1` had no router profile.

### What was fixed:

- [configs/strategy_profile_registry.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/strategy_profile_registry.json) now includes:
  - `ivb1_bull_core`
  - `ivb1_chop_reduced`
  - `ivb1_bear_off`
- [scripts/deploy_foundation.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/deploy_foundation.sh) now deploys the profile registry too
- server-side router + allocator were rebuilt after pushing the new registry

### New live control-plane truth:

- `impulse` is no longer `count=0`
- current server allocator snapshot now shows:
  - `impulse: enabled=1`
  - `risk=1.00`
  - `count=8`
  - `health=OK`
  in `bull_trend`

### New stitched research state:

- Relaunched:
  - `dynamic_core3_impulse_candidate_recent180_v2`
  - `dynamic_core3_impulse_candidate_annual_v2`
- First repaired window signals:
  - `recent180_v2 w01`: sleeves `flat,sloped,impulse` → `+0.87`, PF `1.188`
  - `annual_v2 w01`: sleeves `sloped,impulse` → `-0.71`, PF `0.852`

### What not to do:

- Do not keep quoting `dynamic_system_annual_v1 = +2.97%` as the final annual truth for the intended rebuilt stack.
- It remains useful as an honest result for the **old routed stack**, but not for the newly repaired one.

### New current focus:

- The repaired stitched annual result is now directionally useful but still not promotion-grade:
  - [dynamic_core3_impulse_candidate_annual_v2 summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_161044_dynamic_core3_impulse_candidate_annual_v2/summary.json)
  - `+13.17%`
  - PF `1.2182`
  - DD `5.2386`
  - `6` negative months
- So the next bottleneck is **red-month control**, not “is the system alive at all?”

### New observability truth:

- [bot/diagnostics.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/diagnostics.py) now exposes impulse/IVB1 counters in the compact diag snapshot:
  - `ivb1_sched`
  - `ivb1_try`
  - `ivb1_entry`
  - `ivb1_skip_max_open`
  - `ivb1_skip_portfolio`
  - `ivb1_skip_symbol_lock`
- [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) now surfaces:
  - `ivb1` inside runtime strategy stats
  - `impulse` router profile in `status_full`
  - `impulse-universe` in status/universe notifications

### New research state:

- Launched [range_scalp_v1_annual_repair_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_annual_repair_v1.json)
- This frontier is the current best additive annual repair candidate because:
  - recent-180 range package was already strong
  - annual weakness is mostly too many red months / too long negative streaks
  - the new grid explicitly attacks those failure modes instead of only chasing higher net pnl

### New operator-layer truth:

- Telegram truncation of AI operator messages was not a Telegram platform limit problem.
- The real culprit was [_ai_operator_emit()](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) trimming answers before send.
- This is now repaired:
  - the operator stores a short summary for memory/shadow use
  - but sends the full answer through `tg_send()`, which already knows how to split long messages
- Added short persistent operator memory:
  - [runtime/ai_operator/memory.jsonl](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/ai_operator/memory.jsonl)
  - exposed via [bot/operator_snapshot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/operator_snapshot.py)
  - `/ai_reset` now clears both overlay history and operator memory

### New stitched-annual truth repair:

- The next real bottleneck turned out not to be only sleeve quality, but annual regime truth itself.
- Repaired [scripts/build_regime_state.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_regime_state.py):
  - mixed-sign windows no longer collapse too easily into `bull_chop`
  - added weighted bias scoring and richer diagnostics:
    - `ema_gap_pct`
    - `close_vs_ema55_pct`
    - `mixed_bias`
    - `bull_strength`
    - `bear_strength`
    - `bias_edge_pct`
- Repaired [scripts/run_control_plane_replay.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_control_plane_replay.py):
  - historical `min_hold_cycles=1` now truly allows immediate regime switching
- Extended [scripts/run_dynamic_crypto_annual.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_dynamic_crypto_annual.py):
  - added `--historical-hold-cycles`
  - stitched reports now record that value explicitly
- New corrected stitched annual is now running:
  - [dynamic_core3_impulse_candidate_annual_v3_hold1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_172157_dynamic_core3_impulse_candidate_annual_v3_hold1)
- First signal from the corrected stack:
  - `w01`: `regime=bull_chop`, sleeves `sloped,impulse`, `net=-3.03`, PF `0.148`

Practical meaning:
- `dynamic_core3_impulse_candidate_annual_v2` is still useful as the “first repaired stack” baseline.
- But the next verdict on whether protection layers help or suffocate the bot should come from `annual_v3_hold1`, because the stitched regime logic is now materially closer to the intended historical behaviour.

### Corrected annual verdict:

- [dynamic_core3_impulse_candidate_annual_v3_hold1 summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_172157_dynamic_core3_impulse_candidate_annual_v3_hold1/summary.json)
  - `+7.27%`
  - PF `1.1074`
  - `5` negative months
- This is lower than `annual_v2` (`+13.17%`, PF `1.2182`, `6` negative months), which means:
  - the old repaired annual was still partially flattering the stack
  - the new annual truth is more honest, not “more broken”
  - router truth alone is not enough to get us back to the old headline numbers

### New immediate focus:

- Keep annual repair centered on red-month control, not only raw return.
- `flat` is now the most obvious active sleeve candidate for repair:
  - huge live scan activity historically
  - little realized activation
  - early rows in [flat_horizontal_core_v3_frontier.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/flat_horizontal_core_v3_frontier.json) are alive but not yet promotable
- Next strategy truth should come from:
  - ongoing `range_scalp` annual repair
  - ongoing `flat_horizontal_core_v3_frontier`
  - ongoing `impulse` annual repair
  - newly opened `asc1_annual_repair_v1` for the sloped sleeve

### Overnight repair queue:

- The current useful annual-repair queue is now:
  - `impulse_volume_breakout_v1_annual_repair_v1`
  - `range_scalp_v1_annual_repair_v1`
  - `flat_horizontal_core_v3_frontier`
  - `asc1_annual_repair_v1`
- `support_bounce_v1_regime_gap_repair_v1` has already finished and did **not** become a live candidate:
  - full run completed
  - still failed on PF / DD / negative month constraints
- This means the next bot revival effort is concentrated on the sleeves that still have plausible annual upside, not on already disproven side paths

### Morning strategy truth:

- `impulse` annual repair is now materially successful:
  - many PASS rows already exist
  - best current annual row is roughly `+12.85%`, PF `1.978`, WR `0.642`, DD `2.2835`, `3` red months
- `flat` annual frontier also broke through:
  - best current yearly row is roughly `+7.08%`, PF `5.523`, WR `0.818`, DD `0.8048`, `0` red months
  - strongest basket is `LINKUSDT,LTCUSDT,SUIUSDT`
- `sloped` annual repair failed to promote:
  - no PASS rows
  - still too many negative months / streaks
- `Elder` is currently a logic problem, not a trailing problem:
  - `elder_ts_v2_retest_reclaim_v4` = effectively zero-trade sweep
  - `elder_ts_v2_recent180_focus_v3` = many trades but PF around `0.5`

### New active compare state:

- Promoted the first annual winners into:
  - [core3_flat_impulse_candidate_20260409.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/core3_flat_impulse_candidate_20260409.env)
- Opened a no-sloped policy compare:
  - [portfolio_allocator_policy_no_sloped_20260409.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/portfolio_allocator_policy_no_sloped_20260409.json)
- Running now:
  - `dynamic_core3_flat_impulse_annual_v1`
  - `dynamic_core3_flat_impulse_nosloped_annual_v1`

### 2026-04-09 06:55 UTC sync update

- Server truth after laptop reopen:
  - `systemd` running
  - heartbeat fresh
  - current regime = `bull_chop`
  - control-plane files fresh
- Important code truth:
  - `IVB1` is wired and trying in live; problem is now entry filtering, not missing integration
  - `Elder` had allocator support but was still missing from live bot wiring
- Fixed now:
  - wired `elder_triple_screen_v2` into [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py)
  - added live env/risk plumbing, per-symbol engine, scheduler hook, and status/universe visibility
  - upgraded [bot/diagnostics.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/diagnostics.py) with grouped `IVB1` and `Elder` no-signal reason counters
  - softened [elder_triple_screen_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/elder_triple_screen_v2.py) defaults toward crypto-realistic values (`OSC 42/58`, `retest=5`, `TP=2.5 ATR`, `cooldown=18`, `daily cap=20`)
- New active runs:
  - `elder_ts_v2_live_repair_v1`
  - `core3_flat_impulse_nosloped_wf360_v1`
- New validator truth:
  - [run_dynamic_crypto_walkforward.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_dynamic_crypto_walkforward.py) now exists and should replace static walk-forward whenever we want a promotion-grade answer
  - it uses historical `regime + router + allocator + health timeline`, not a frozen symbol list
  - first window on `dynamic_core3_flat_impulse_nosloped_wf360_v1` came back `+1.58`, PF `inf`, DD `0.02`, `3` trades, `pass=False`
- New live-debug truth:
  - `flat` and `IVB1` were still too opaque in production because `flat` had no reason-level no-signal telemetry and most `IVB1` misses collapsed into `other`
  - this is now fixed in code and deployed
  - current server params still explain why the next likely blockers are strict `flat` conditions rather than “bot is dead”:
    - `ARF1_SIGNAL_TF=60m`
    - `ARF1_MIN_RSI=58`
    - `ARF1_REJECT_BELOW_RES_ATR=0.12`
  - wait for the next production pulses before changing thresholds blindly; the new counters should tell us whether the main blocker is `same_bar`, `RSI`, `touch/reject`, or `IVB1` breakout quality
- New annual-repair truth:
  - the big stitched weakness is not generic; it is concentrated in noisy `bear_chop`
  - current evidence says:
    - `breakdown` loses money in that quadrant
    - `flat` helps there, but not enough yet
  - current sloped annual verdict was also incomplete because the first annual repair was short-only
- New active repair runs:
  - `bear_chop_core_repair_v1`
  - `asc1_bidirectional_annual_probe_v1`
  - `flat_frequency_repair_v1`
  - `dynamic_core4_flat_impulse_bounce_annual_v1`
- New interpretation update:
  - the missing long-horizontal quadrant is no longer hypothetical
  - `support_bounce` already has standalone annual candidates around `+16%` with `3` red months
  - the next question is portfolio additivity, not whether the idea itself exists
- Current package hierarchy is unchanged until the new rolling run finishes:
  - near-term core candidate remains `breakdown + flat + impulse`
  - `sloped` stays out of the near-term core unless new evidence overturns the no-sloped advantage
  - `Elder` is no longer “not wired”, but it still needs fresh evidence before any promotion talk
