# Weekly DeepSeek Research & Bot Audit — 2026-04-20 (Mon 09:00 EEST)

*Automated run of `deepseek-weekly-research` scheduled task. Generated from Claude VM sandbox.*

## Critical: scheduled-task environment has no outbound network

Both remote calls required by the skill failed:

- **SSH to `root@64.226.73.119`** via `/sessions/stoic-upbeat-ramanujan/mnt/.ssh/by-bot` → `connect to host 64.226.73.119 port 22: Network is unreachable`. `ping` and `nc -zv 64.226.73.119 22` both fail at the kernel level (no route).
- **DeepSeek API (`api.deepseek.com`)** via the local `bot.deepseek_autoresearch_agent.audit_bot_full()` call → `HTTPSConnectionPool ... ProxyError('Unable to connect to proxy', 'Tunnel connection failed: 403 Forbidden')`.

Steps 1–4 of the skill (`systemctl status bybot`, server-side audit via DeepSeek, TG send) are therefore blocked. Only Step 5 (local backtest_runs scan) is executable.

**Recommendation**: move the SSH + DeepSeek portions off this scheduled task. Either (a) rely on the server's own cron to run the audit and post to Telegram, and have this task only poll local autoresearch progress, or (b) run the skill from a host with network egress to the droplet and DeepSeek.

## Local autoresearch progress

**Source**: `/sessions/stoic-upbeat-ramanujan/mnt/bybit-bot-clean-v28/backtest_runs/`.

The four configs named in the skill are stale:

| config | latest run | result |
|---|---|---|
| `breakdown_shorts_v1` | (none) | no autoresearch dir found |
| `full_stack_v2_overnight` | (none) | no autoresearch dir found |
| `flat_arf1_expansion_v2` | 2026-04-04 | 540 rows, **0 passing** |
| `triple_screen_elder_friend_v10` | (none) | no autoresearch dir found |

The skill's config list needs updating — real activity has moved on.

### Most recent meaningful sweeps

**`att1_initial_sweep_v1`** (`autoresearch_20260418_070610_att1_initial_sweep_v1`, 1567 rows, 1568 passing). Top 5 unique by score:

| tag | pf | wr | trades | dd | score |
|---|---|---|---|---|---|
| r424 | 1.32 | 0.58 | 402 | 7.27 | 34.37 |
| r454 | 1.31 | 0.58 | 396 | 7.45 | 31.85 |
| r343 | 1.29 | 0.58 | 409 | 7.27 | 31.18 |
| r427 | 1.27 | 0.57 | 454 | 8.68 | 30.97 |
| r451 | 1.32 | 0.59 | 364 | 7.00 | 29.89 |

Follow-up portfolio runs (`portfolio_20260419_11*_att1_initial_sweep_v1_r884…r892`) confirm these candidates are in the portfolio-test stage as of 2026-04-19.

**Other recent top passes**:

- `bear_chop_core_repair_v1` (2026-04-11): pf=2.17, wr=0.59, trades=105, dd=3.01, score=44.75
- `asm1_initial_sweep_v1` (2026-04-11): pf=1.53, wr=0.63, trades=171, dd=4.57, score=26.53
- `flat_live_frequency_v3` (2026-04-11): pf=1.83, wr=0.55, trades=44, dd=3.30, score=15.10
- `ivb1_wider_universe_v1` (2026-04-11): pf=1.58, wr=0.56, trades=39, dd=1.78, score=7.00
- `att1_focused_pivot_sweep_v1` (2026-04-11): pf=1.25, wr=0.57, trades=321, dd=7.90, score=17.82

## Summary

- **Server bot status**: UNKNOWN — SSH blocked by sandbox network policy (not a bot issue).
- **DeepSeek audit**: NOT RUN — api.deepseek.com blocked by proxy (403).
- **Critical issues found**: none detectable without SSH/API access.
- **Configs named in skill**: 3 of 4 have no autoresearch runs; the 1 that ran has 0 passing. Skill config list is stale — update to `att1_initial_sweep_v1`, `bear_chop_core_repair_v1`, `asm1_initial_sweep_v1`, `flat_live_frequency_v3`, `ivb1_wider_universe_v1`.
- **Best passing candidate this week**: `bear_chop_core_repair_v1_r971` (pf=2.17, dd=3.01) — though sweep is ~9 days old.
- **Most active pipeline**: `att1_initial_sweep_v1` → portfolio stage on 2026-04-19.
