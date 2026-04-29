# Server Cron Audit — 2026-04-29

## Scope

Read-only audit on droplet `64.226.73.119` to answer whether AI/nightly automation is alive on the real server, not just in the local mirror.

## Findings

### Managed crons

The server has the expected managed cron block installed. Relevant entries include:

- `build_regime_state.py` hourly
- `build_symbol_router.py` every 4 hours
- `build_portfolio_allocator.py` hourly
- `control_plane_watchdog.py --repair` every 15 minutes
- `build_operator_snapshot.py --quiet` hourly
- `run_nightly_research_queue.py --quiet` hourly at minute 17
- `build_self_audit_report.py --quiet` every 2 hours
- `deepseek_weekly_cron.py --quiet` Sundays 22:30 UTC
- `auto_apply_research_winner.py` daily at 06:00 UTC
- `live_vs_backtest_monitor.py` every 4 hours

### Nightly research queue

Server-side `runtime/research_nightly/status.json` is fresh:

- mtime `2026-04-29 07:17:01 UTC`
- state `ok`
- active process count `0`
- proposed task: `bear_chop_plus_range_probe_v1`
- cooldown/launch-limit skips present

This means the server-side queue is alive. The older local timestamp was a stale mirror, not the truth.

### DeepSeek weekly

`logs/deepseek_weekly.log` last mtime:

- `2026-04-19 22:30:03 UTC`

Tail shows the weekly job did run and created:

- `/root/by-bot/docs/weekly_reports/deepseek_weekly_20260406_080002.md`

But Telegram was not configured in that run:

- `Telegram not configured (TG_TOKEN / TG_CHAT_ID missing).`

So DeepSeek weekly is installed, but it needs a follow-up check for why there is no 2026-04-26 log entry and whether the expected Telegram/report delivery path is configured.

### Autoresearch dirs on server

Most recent server-side autoresearch dirs shown by audit:

- `backtest_runs/autoresearch_20260421_133111_elder_ts_v3_macro_relax_v1`
- `backtest_runs/autoresearch_20260421_133123_elder_ts_v3_macro_relax_v1`
- `backtest_runs/autoresearch_20260420_055535_elder_ts_v3_macro_relax_v1`
- `backtest_runs/autoresearch_20260419_045148_breakout_live_bridge_v8_nocache`
- `backtest_runs/autoresearch_20260419_000250_hzbo1_live_bridge_v1_nocache`
- `backtest_runs/autoresearch_20260418_124041_att1_focused_pivot_sweep_v2_nocache`

This suggests the hourly queue is currently proposing tasks, but not necessarily launching full new runs every hour due cooldown/launch-limit logic.

## Verdict

AI/automation status is `PARTIAL`.

- Control-plane automation is alive.
- Nightly research queue is alive on the server and status is fresh.
- DeepSeek weekly cron is installed, but reporting/log freshness needs a follow-up.
- Operator snapshot cron is installed, but this audit command did not successfully print its snapshot contents; check separately if needed.

## Next

1. Keep canary v2 live unchanged.
2. Do not rerun `setup_server_crons.sh` yet; crons are already installed.
3. Debug DeepSeek weekly delivery separately: env keys, log after next Sunday, and report path.
4. Add the AI operator context improvement later: live PnL, active flags, last backtest, last trade events, and canary counters.
