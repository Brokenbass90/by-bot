# Session Cache — Project State for AI Continuity
> READ THIS FIRST when continuing from a previous session.
> Last updated: 2026-03-18

## Project Overview
Algorithmic trading bot operating on 3 markets:
- **Crypto** (Bybit Futures, USDT perpetuals) — LIVE on DigitalOcean server
- **US Equities** (Alpaca, paper trading) — monthly swing strategy
- **Forex** (MT5) — planning stage

Owner: Nikolay Bulgakov (brokenbass1990@gmail.com)
Server: 64.226.73.119 (root, SSH key: `.ssh/by-bot`)
GitHub: github.com/Brokenbass90/by-bot (branch: codex/dynamic-symbol-filters)

## Critical State

### What's Working
- **Breakout strategy** (inplay_breakout): 717 trades/year, WR 65%, +$70/year on $100. ALL 12 months positive.
- **Sloped channel** (alt_sloped_channel_v1): ATOM shorts only, 17 trades, WR 58.8%, PF 2.49.
- **Equities monthly** (equities_monthly_research_sim.py): +76.7% compounded/19mo, WR 63.9%.

### What's NOT Working
- **Quality gate blocked all trades**: `BREAKOUT_QUALITY_MIN_SCORE=0.52` in .env → set to 0.0
- **Triple Screen v132**: Loses money with default settings on ALL coins tested. Needs per-coin autoresearch.
- **BTC strategies**: 6 files, none pass autoresearch constraints.

### What Needs Deploying
1. Run `bash scripts/deploy_full_20260318.sh` from Mac terminal
2. This pushes to GitHub, pulls on server, sets quality=0.0, restarts bot

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

## Backtest Results Summary (360 days)

| Strategy | Coins | Trades | WR | Net PnL | PF | Months + |
|----------|-------|--------|-----|---------|------|---------|
| Breakout (quality=0) | 8 | 717 | 65.1% | +$70.40 | 1.59 | 12/12 |
| Sloped ATOM | 1 | 17 | 58.8% | +$4.89 | 2.49 | 6/7 |
| Combined | 8+1 | 734 | ~64.8% | +$75.29 | ~1.62 | 12/12 |
| Equities (19mo) | 5 stocks | 36 | 63.9% | +76.7% | - | 16/19 |
| Triple Screen | ANY | varies | <35% | NEGATIVE | <0.6 | — |

## Next Steps (in priority order)
1. Deploy quality gate fix → bot starts trading
2. Monitor breakout 1-2 weeks
3. Enable sloped channel (ATOM)
4. Run autoresearch for TS132 + sloped families (can run for days)
5. Fetch extended equities data (50 stocks, 4 years)
6. Run equities autoresearch with expanded universe
7. Set up cron jobs for weekly monitoring + autoresearch
8. Scale capital as results prove out

## Important Context for AI
- Owner has limited technical knowledge. Provide exact commands and scripts, don't assume manual steps.
- Owner may have limited internet access. Bot must be as autonomous as possible.
- Financial situation is tight. Every optimization matters.
- Always update this file and WORKLOG.md after making changes.
- Always test before deploying. Use backtests to validate.
- The autoresearch tool (`run_strategy_autoresearch.py`) can run for hours/days — that's fine and expected.
