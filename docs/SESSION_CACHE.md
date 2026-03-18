# Session Cache — Project State for AI Continuity
> READ THIS FIRST when continuing from a previous session.
> Last updated: 2026-03-18 (session 2 — Claude Sonnet)

## Project Overview
Algorithmic trading bot operating on 3 markets:
- **Crypto** (Bybit Futures, USDT perpetuals) — LIVE on DigitalOcean server
- **US Equities** (Alpaca, paper trading) — monthly swing strategy
- **Forex** (MT5) — planning stage

Owner: Nikolay Bulgakov (brokenbass1990@gmail.com)
Server: 64.226.73.119 (root, SSH key: `.ssh/by-bot`)
GitHub: github.com/Brokenbass90/by-bot (branch: codex/dynamic-symbol-filters)

## Critical State (as of 2026-03-18 session 2)

### Server Status RIGHT NOW
- Bot running: YES (PID 532140, restarted 2026-03-18 ~13:15 UTC)
- Quality gate: FIXED (`BREAKOUT_QUALITY_MIN_SCORE=0.0`)
- Active strategies: `ENABLE_BREAKOUT_TRADING=1`, `ENABLE_MIDTERM_TRADING=1`
- Server branch: `codex/dynamic-symbol-filters` at commit `5c8e541`
- **Local branch is 2 commits ahead of server** — new code (sloped+TS132 integration) not deployed yet
- GitHub push BLOCKED: no SSH key for GitHub on Mac, no `gh` CLI installed
  → Solution: install `brew install gh && gh auth login` OR use GitHub Desktop
  → Codex can do the push when it wakes up

### What's Working
- **Breakout strategy**: running live, quality gate fixed today
- **ETH Midterm V1** (btc_eth_midterm_pullback.py): 80 signals/yr, WR 55%, PF 2.30, TotalR +43.5R. Keep as-is.
- **Sloped channel** (alt_sloped_channel_v1): **ATOM+LINK shorts**, WR 70%, PF 3.85 (best result). Ready for live.
- **Equities monthly** (+76.7% compounded/19mo).

### What's NOT Working / Needs Work
- **Triple Screen v132**: Loses money with ALL tested settings. Needs autoresearch (run_strategy_autoresearch.py).
- **GitHub push**: SSH key `by-bot` is only for server, not GitHub.
- **New strategies not on server yet** (2 commits pending push).

### Flat Strategy Findings (2026-03-18 Session 2)
Best result: `alt_sloped_channel_v1` on **LINKUSDT + ATOMUSDT (shorts only)**
- 360 days, 20 trades, WR 70%, PF 3.85, Net PnL +11.6%, Max DD 1.8%
- Config: ASC1_ALLOW_LONGS=0, ASC1_MAX_ABS_SLOPE_PCT=2.0, ASC1_MIN_RANGE_R2=0.25
- Adding SOL/AVAX/ETH/SUI doesn't improve much (stays at PF 3.74, same 20 trades)
- Adding BNB: 25 trades, PF 2.72 (moderate)
- **Action: deploy sloped channel for ATOM+LINK after GitHub push**

### ETH Midterm V2 (built 2026-03-18)
- File: `strategies/btc_eth_midterm_pullback_v2.py`
- Added: 4H sloped channel filter + dynamic TP + two-phase exits
- Backtest: V1 is still better (PF 2.30 vs 2.01, TotalR +43.5 vs +15.6)
- Conclusion: channel filter as ENTRY gate hurts. V1 is better. V2 kept for future reference.
- **Do NOT deploy V2. Keep V1 live.**

### What Needs Deploying (next session)
1. GitHub push (Codex or `brew install gh && gh auth login` on Mac)
2. `git pull` on server
3. Set on server: `ENABLE_SLOPED_TRADING=1`, `ASC1_ALLOW_LONGS=0`, `ASC1_SYMBOL_ALLOWLIST=LINKUSDT,ATOMUSDT`
4. Run autoresearch for TS132: `python3 scripts/run_strategy_autoresearch.py configs/autoresearch/triple_screen_adaptive_v1.json`

## File Map (Key Files)

### Bot Core
- `smart_pump_reversal_bot.py` — Main bot (6500+ lines). All strategies dispatch from `detect()` function (~line 5560).
- `.env` — Configuration (GITIGNORED). Server copy at `/root/by-bot/.env`.
- `trade_state.py` — Trade lifecycle state machine.

### Strategies
- `strategies/inplay_breakout.py` — Main breakout (WORKING)
- `strategies/alt_sloped_channel_v1.py` — Sloped channel (WORKING for ATOM)
- `strategies/sloped_channel_live.py` — Live wrapper for sloped channel
- `archive/strategies_retired/triple_screen_v132.py` — Triple screen (NEEDS TUNING)
- `strategies/btc_*.py` — 6 BTC strategies (ALL NEED WORK)

### Equities
- `scripts/equities_monthly_research_sim.py` — Monthly backtest simulator
- `scripts/equities_alpaca_paper_bridge.py` — Paper trading executor
- `scripts/equities_midmonth_monitor.py` — NEW: weekly position health check
- `scripts/equities_fetch_extended_universe.py` — NEW: fetch 50-stock data
- `configs/alpaca_paper_local.env` — Alpaca API keys and config

### Autoresearch
- `scripts/run_strategy_autoresearch.py` — Grid search optimizer (Karpathy-style)
- `configs/autoresearch/triple_screen_adaptive_v1.json` — TS132 per-coin search
- `configs/autoresearch/flat_slope_adaptive_families_v1.json` — Sloped channel families
- `configs/autoresearch/equities_monthly_v10_extended_universe.json` — NEW: 20-stock equities

### Infrastructure
- `scripts/deploy_full_20260318.sh` — One-click deploy to server
- `configs/symbol_filters_profiles.json` — Dynamic symbol filter config
- `scripts/build_symbol_filters.py` — Auto-builds symbol allowlist every 30min

## Enable Flags (in .env / smart_pump_reversal_bot.py)
```
ENABLE_BREAKOUT_TRADING=1     ← ON (main strategy)
ENABLE_SLOPED_TRADING=0       ← OFF (enable after observation)
ENABLE_TS132_TRADING=0        ← OFF (enable after autoresearch)
ENABLE_INPLAY_TRADING=0       ← OFF
ENABLE_RANGE_TRADING=0        ← OFF (dead code)
ENABLE_RETEST_TRADING=0       ← OFF
ENABLE_MIDTERM_TRADING=0      ← OFF
```

## Server Info
- IP: 64.226.73.119
- User: root
- SSH key: `/Users/nikolay.bulgakov/.ssh/by-bot` (also in project `.ssh/by-bot`)
- Bot directory: `/root/by-bot` (or `/root/bybit-bot-clean-v28`)
- Bot runs in: screen session `bot` or systemd service
- Telegram: bot token in .env, chat 319077869

## Backtest Results Summary (360 days, updated 2026-03-18)

| Strategy | Coins | Trades | WR | Net PnL | PF | Status |
|----------|-------|--------|-----|---------|------|--------|
| Breakout (quality=0) | 17 | 717 | 65.1% | +70.4% | 1.59 | ✅ LIVE |
| ETH Midterm V1 | ETH | 80 | 55% | +43.5R | 2.30 | ✅ LIVE |
| Sloped ATOM+LINK shorts | 2 | 20 | 70.0% | +11.6% | 3.85 | 🔜 READY |
| Sloped ATOM+LINK+BNB | 3 | 25 | 64% | +10.5% | 2.72 | option |
| Triple Screen v132 | ANY | — | <35% | NEGATIVE | <0.6 | ❌ needs research |
| Equities (19mo) | 5 stocks | 36 | 63.9% | +76.7% | — | ✅ paper |

## Strategies NOT to Deploy
- `btc_eth_midterm_pullback_v2.py` — backtested worse than v1, keep for reference only
- Any TS132 config without autoresearch confirmation
- BTC-specific strategies (none pass constraints yet)

## Next Steps (in priority order)
1. **GitHub push** → `brew install gh && gh auth login` then `git push origin codex/dynamic-symbol-filters`
2. **Server pull** → `ssh -i ~/.ssh/by-bot root@64.226.73.119 "cd /root/by-bot && git pull origin codex/dynamic-symbol-filters"`
3. **Enable sloped channel** on server → add to .env: `ENABLE_SLOPED_TRADING=1`, `ASC1_ALLOW_LONGS=0`, `ASC1_SYMBOL_ALLOWLIST=LINKUSDT,ATOMUSDT`
4. **Run TS132 autoresearch** on server in background
5. Expand equities to 20 stocks (config ready: `configs/autoresearch/equities_monthly_v10_extended_universe.json`)
6. Forex: MT5 demo setup when ready

## Important Context for AI
- Owner has limited technical knowledge. Provide exact commands and scripts, don't assume manual steps.
- Owner may have limited internet access. Bot must be as autonomous as possible.
- Financial situation is tight. Every optimization matters.
- Always update this file and WORKLOG.md after making changes.
- Always test before deploying. Use backtests to validate.
- The autoresearch tool (`run_strategy_autoresearch.py`) can run for hours/days — that's fine and expected.

## 2026-03-18 Evening Resume (Codex)

### Live status now
- Bot is alive.
- Fresh `2h` diag:
  - `breakout_try=2699`, `midterm_try=53`, `entry=0`
  - `skip_quality=0`
  - `ws_connect=8`, `ws_disconnect=8`, `handshake_timeout=0`
  - status `WARN`
- Fresh `12h` diag:
  - `breakout_try=13672`, `midterm_try=311`, `entry=0`
  - `ws_connect=43`, `ws_disconnect=44`, `handshake_timeout=0`
  - status `WARN`
- Reading:
  - live is not dead
  - quality gate is no longer the blocker
  - main no-signal reason is still `impulse_weak`

### Important code/document mismatch
- `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/AUDIT_20260318.md` says sloped/TS132 are not wired into live.
- That is already stale locally.
- Local HEAD `32fc890` has:
  - `ENABLE_SLOPED_TRADING`
  - `ENABLE_TS132_TRADING`
  - live hooks in `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py`
  - live wrapper `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/sloped_channel_live.py`
- But local branch is still ahead of origin/server, so wiring exists locally and is not yet deployed.

### TS132 audit and correction
- Compared friend's Pine file:
  - `/Users/nikolay.bulgakov/Downloads/triple_screen_v13_2_PROD (1).txt`
- Against our port:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/archive/strategies_retired/triple_screen_v132.py`
- Main mismatch found:
  - Pine uses break-even activation and delayed trailing activation.
  - Our previous port simplified this and could optimize the wrong strategy shape.
- Fixed locally:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/signals.py`
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/trade_state.py`
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/engine.py`
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/portfolio_engine.py`
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py`
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/archive/strategies_retired/triple_screen_v132.py`
- New fields now supported:
  - `be_trigger_rr`
  - `be_lock_rr`
  - `trail_activate_rr`

### New TS132 search spec
- Added:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/triple_screen_adaptive_v2_fidelity.json`
- Focus:
  - friend's actual live-ish symbols: `KSM, STRK, AVAX, AXS, ETH`
  - Pine-like knobs: trade mode, oscillator type/period, EMA length, SL/TP ATR, BE %, volume filter, max signals/day, exec mode

### Current TS132 reality
- Quick smoke on `KSMUSDT` with Pine-like defaults:
  - run: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260318_193959_ts132_fidelity_smoke_ksm/summary.csv`
  - result: `2` trades, `-3.24`, PF `0.0`
- Interpretation:
  - fidelity is better now
  - defaults are still not enough
  - next step is long autoresearch or exact per-coin settings from the friend

### TS132 active queue
- Main active search now:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/triple_screen_adaptive_v2_stage1.json`
- Why:
  - `v2_fidelity` full grid is too wide for immediate productive iteration
  - stage-1 narrows the search to the friend's currently active-looking symbols and the highest-signal knobs
- Tiny slice result from `v2_fidelity`:
  - `6` runs completed
  - no passing candidate yet
  - best row still failed on trades/PF/net for `KSMUSDT`

## 2026-03-18 Late Evening Follow-up (Codex)

### Live status now
- Fresh `2h` diag:
  - `breakout_try=2748`, `midterm_try=52`, `entry=0`
  - `skip_quality=0`
  - `ws_connect=6`, `ws_disconnect=6`, `handshake_timeout=0`
  - status `WARN`
  - dominant no-signal: `impulse_weak=74.04%`
- Fresh `12h` diag:
  - `breakout_try=13835`, `midterm_try=310`, `entry=0`
  - `skip_quality=0`
  - `ws_connect=44`, `ws_disconnect=45`, `handshake_timeout=0`
  - status `WARN`
  - dominant no-signal: `impulse_weak=60.61%`
- Reading:
  - live is alive
  - infra is noisy but not failing
  - weak market remains the main reason for no entries

### Push/deploy blocker
- Local branch is still ahead of origin by `4` commits.
- Direct `git push origin codex/dynamic-symbol-filters` failed:
  - `git@github.com: Permission denied (publickey)`
- No saved HTTPS deploy token exists on this Mac:
  - `~/.by-bot-github-token` is missing
- Practical meaning:
  - code is ready locally
  - deploy is blocked on GitHub auth, not on code

### Safer sloped canary prep
- Added isolated live-canary controls in `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py`:
  - `SLOPED_RISK_MULT`
  - `SLOPED_MAX_OPEN_TRADES`
- Why:
  - lets sloped run tiny without changing the global core risk
  - keeps sloped concurrency capped separately
- Important limitation:
  - sloped still respects the global portfolio gate, so it is not a fully separate process/account sleeve yet

### New deploy helper
- Added:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/deploy_sloped_atom_canary_20260318.sh`
- Purpose:
  - push via HTTPS token
  - pull on server
  - enable `ENABLE_SLOPED_TRADING=1`
  - keep `ENABLE_TS132_TRADING=0`
  - apply the winning `ATOMUSDT` canary `ASC1` settings
  - avoid touching global `RISK_PER_TRADE_PCT` / `MAX_POSITIONS`

### Updated sloped canary env examples
- `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/flat_slope_atom_canary.env.example`
- `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/flat_slope_link_atom_canary.env.example`
- These now reflect actual live usage:
  - `ENABLE_SLOPED_TRADING=1`
  - `ENABLE_TS132_TRADING=0`
  - `SLOPED_RISK_MULT=0.10`
  - `SLOPED_MAX_OPEN_TRADES=1`

### Alpaca extended-universe search
- Old `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/equities_monthly_v10_extended_universe.json` is not compatible with `run_strategy_autoresearch.py`.
- Added runner-compatible replacement:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/equities_monthly_v10_extended_universe_autoresearch.json`

### Current active queues
- `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/triple_screen_adaptive_v2_stage1.json`
- `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/flat_slope_adaptive_families_v1.json`
- `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/equities_monthly_v10_extended_universe_autoresearch.json`
