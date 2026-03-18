# Trading Bot Development Roadmap
> Last updated: 2026-03-18

## Current State (March 2026)

### Revenue Streams
| Stream | Status | Strategy | Capital | Expected Monthly |
|--------|--------|----------|---------|-----------------|
| Crypto Breakout | LIVE (blocked) | inplay_breakout | $100 | ~5.9% ($5.90) |
| Crypto Sloped | READY | alt_sloped_channel_v1 (ATOM) | $100 shared | ~0.7% ($0.70) |
| Crypto Triple Screen | IN DEVELOPMENT | triple_screen_v132 | $100 shared | TBD |
| US Equities | PAPER TRADING | monthly swing (5 stocks) | $500 paper | ~3.1% ($15.50) |
| Forex | PLANNING | sloped channel adaptation | $0 | Future |

### Blocking Issues
1. **BREAKOUT_QUALITY_MIN_SCORE=0.52** blocks ALL crypto trades → FIX: set to 0.0
2. Triple Screen needs per-coin autoresearch before deployment
3. Equities limited to 5 stocks, needs expansion

---

## Phase 1: Unblock Revenue (This Week)
- [ ] Deploy `BREAKOUT_QUALITY_MIN_SCORE=0.0` to server
- [ ] Run `bash scripts/deploy_full_20260318.sh` from Mac terminal
- [ ] Monitor breakout trades for 1 week via Telegram
- [ ] Verify dynamic symbol filter is rotating coins

**Expected outcome:** Bot starts trading crypto breakouts (~60 trades/month)

## Phase 2: Multi-Strategy Crypto (Weeks 1-2)
- [ ] Enable `ENABLE_SLOPED_TRADING=1` on server (ATOM only, shorts only)
- [ ] Run autoresearch for Triple Screen: `python3 scripts/run_strategy_autoresearch.py configs/autoresearch/triple_screen_adaptive_v1.json`
- [ ] Run autoresearch for sloped channel families: `python3 scripts/run_strategy_autoresearch.py configs/autoresearch/flat_slope_adaptive_families_v1.json`
- [ ] Review autoresearch results, deploy winning configs

**Expected outcome:** 2 active crypto strategies (breakout + sloped ATOM)

## Phase 3: Expand Equities (Weeks 2-4)
- [ ] Fetch extended universe data: `python3 scripts/equities_fetch_extended_universe.py --years 4`
- [ ] Run equities autoresearch with 20 stocks: `python3 scripts/run_strategy_autoresearch.py configs/autoresearch/equities_monthly_v10_extended_universe.json`
- [ ] Set up mid-month cron: `0 15 * * 3 cd /root/by-bot && bash scripts/run_equities_midmonth_check.sh >> logs/alpaca_midmonth.log 2>&1`
- [ ] Switch from 5 to 20 stocks in Alpaca config
- [ ] Add dynamic regime to monthly refresh

**Expected outcome:** 20-stock equities with weekly monitoring, higher WR

## Phase 4: Automation & Intelligence (Month 2)
- [ ] Set up weekly autoresearch cron for crypto strategies
- [ ] Implement auto-config-reload from autoresearch winners
- [ ] DeepSeek AI overlay prototype (API scoring for trade decisions)
- [ ] Test BTC strategies via dedicated autoresearch runs
- [ ] If Triple Screen finds winning configs → enable `ENABLE_TS132_TRADING=1`

**Expected outcome:** Self-tuning strategies, AI-assisted decisions

## Phase 5: Scale & Diversify (Month 3+)
- [ ] Increase crypto capital ($100 → $500 → $1000+) based on live track record
- [ ] Transition Alpaca from paper to real ($500 → $2000+)
- [ ] Adapt sloped channel for Forex (MT5 demo first)
- [ ] Add more equities strategies (sector rotation, earnings momentum)
- [ ] Portfolio-level risk management across all streams
- [ ] Weekly automated performance reports

**Expected outcome:** Multi-asset portfolio generating consistent monthly income

---

## Key Commands Reference

### Deploy to Server
```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
bash scripts/deploy_full_20260318.sh
```

### Run Autoresearch (on server)
```bash
# Triple Screen per-coin optimization
python3 scripts/run_strategy_autoresearch.py configs/autoresearch/triple_screen_adaptive_v1.json

# Sloped channel family search
python3 scripts/run_strategy_autoresearch.py configs/autoresearch/flat_slope_adaptive_families_v1.json

# Equities extended universe
python3 scripts/run_strategy_autoresearch.py configs/autoresearch/equities_monthly_v10_extended_universe.json
```

### Server Cron Jobs (add via `crontab -e`)
```cron
# Monthly equities autopilot (1st of month, market open)
30 9 1 * * cd /root/by-bot && bash scripts/run_equities_alpaca_monthly_autopilot.sh >> logs/alpaca_monthly.log 2>&1

# Weekly mid-month check (Wednesday 15:00 UTC)
0 15 * * 3 cd /root/by-bot && bash scripts/run_equities_midmonth_check.sh >> logs/alpaca_midmonth.log 2>&1

# Weekly autoresearch for crypto (Sunday 02:00 UTC)
0 2 * * 0 cd /root/by-bot && python3 scripts/run_strategy_autoresearch.py configs/autoresearch/triple_screen_adaptive_v1.json >> logs/autoresearch.log 2>&1
```

### Key .env Changes for Server
```bash
# Phase 1 (NOW)
BREAKOUT_QUALITY_MIN_SCORE=0.0

# Phase 2 (after 1-2 weeks observation)
ENABLE_SLOPED_TRADING=1
ASC1_ALLOW_LONGS=0
ASC1_ALLOW_SHORTS=1
ASC1_SYMBOL_ALLOWLIST=ATOMUSDT

# Phase 4 (after autoresearch finds winners)
ENABLE_TS132_TRADING=1
TS132_SYMBOLS=<from_autoresearch>
```

---

## Architecture

```
                    ┌─────────────────┐
                    │   Telegram Bot   │
                    │   (alerts/logs)  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
    ┌─────────▼───┐  ┌──────▼──────┐  ┌───▼──────────┐
    │  Bybit Bot  │  │ Alpaca Bot  │  │ Forex (MT5)  │
    │ (crypto)    │  │ (equities)  │  │ (future)     │
    └──────┬──────┘  └──────┬──────┘  └──────────────┘
           │                │
    ┌──────┴──────┐  ┌──────┴──────┐
    │ Strategies  │  │ Monthly Sim │
    │ - breakout  │  │ + midmonth  │
    │ - sloped    │  │ + autopilot │
    │ - ts132     │  │ + earnings  │
    └──────┬──────┘  └─────────────┘
           │
    ┌──────┴──────┐
    │ Autoresearch│ ← weekly cron
    │ (Karpathy)  │
    └─────────────┘
```

## Notes for Other AI Assistants
If you're another AI continuing this project, read these files in order:
1. `docs/SESSION_CACHE.md` — current state, what's done, what's next
2. `docs/WORKLOG.md` — detailed session history
3. `docs/ROADMAP.md` — this file
4. `.env` — current configuration (gitignored, check server)
5. `smart_pump_reversal_bot.py` — main bot (6500+ lines)
