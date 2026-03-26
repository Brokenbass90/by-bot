# Trading Bot Development Roadmap
> Last updated: 2026-03-26

## Current Operational Focus (2026-03-26)

This block is the current source of truth. Older sections below remain useful as history, but they no longer describe the live stack accurately.

### Immediate Priorities
1. Finish env/deploy cleanup so `.env` and `/root/by-bot/.env` are the only operational sources of truth.
2. Keep the 5-sleeve live stack stable and observable:
   - `breakout`
   - `midterm`
   - `sloped`
   - `flat`
   - `breakdown`
3. Lock in the recent live sleeve fixes:
   - `sloped/flat/breakdown` engine init now recovers correctly
   - sleeve counters now show real scheduling and try activity
   - next target is safer entry flow, not basic engine survival
4. Add operator/control-plane maturity without giving AI unsafe authority:
   - evidence-first proposals
   - approval-gated changes
   - bounded research launch
   - dynamic symbol/family rotation with operator review, not blind auto-rollout
   - later add internet/news context as advisory filter for crypto and equities
5. Reduce deploy confusion before any bigger rollout or cleanup delete pass.

### Best Current Strategic Result
- `portfolio_20260325_172613_new_5strat_final`
- `+100.93%`
- `PF 2.078`
- `WR 55.8%`
- `446 trades`
- `DD 3.65%`
- `0` red months by raw trade aggregation

### Current Research Order
1. `breakout side-split` as the most promising core improvement
2. `midterm` repair as the weakest live sleeve
3. `TS132 / Elder` via symbol pockets, not one setup for all coins
4. `Alpaca` red-month repair before any real-money rollout
5. `micro scalper` only after the minute-level backtest path is honest
6. `trendline break/retest` as separate long and short sleeves after current live stack is safer
7. add dynamic weak-market / quiet-asset sleeves:
   - auto-find symbols and families for flat/chop conditions
   - keep new listings under watchlist/canary flow before live enable
   - do not forget breakout extensions and low-activity asset logic

### Cleanup Rule
- No blind deletes.
- First classify active vs legacy vs historical-oneoff.
- Then remove or archive in small reversible batches.

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
