# Project Journal

> One entry per session. Most recent at top.
> Format: date | who | what was done | key findings | next

---

## 2026-03-28 | Claude (sessions 13–14)

**Done:**
- Built `scripts/dynamic_allowlist.py` — live Bybit market scanner with per-strategy profiles
  (ASC1, ARF1, BREAKDOWN), optional backtest gate, dry-run mode, cron-ready
- Full Alpaca diagnosis: monthly momentum strategy has 1 trade (XOM, -3.79% stopped out March 2).
  Root cause: no regime filter. Market was risk-off (SPY selloff), strategy entered anyway.
- Identified WF-validated intraday strategies already sitting in backtest_runs:
  TSLA breakout_continuation (67% WF), GOOGL grid_reversion (67% WF), JPM grid_reversion (67% WF)
- Updated ROADMAP.md with full priority queue and 12-month architecture blueprint
- Created JOURNAL.md (this file)

**Key findings:**
- First Alpaca fix to test: add SPY 50-SMA regime gate to equities_monthly_research_sim.py
- The intraday WF strategies are already validated — they just need an execution bridge
- dynamic_allowlist.py ready to use, needs first dry-run from local machine

**Pending (user to run locally):**
- `python3 scripts/dynamic_allowlist.py --dry-run`
- `python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/pump_fade_simple_meme.json`

---

## 2026-03-28 | Claude (sessions 11–12)

**Done:**
- Full pump_fade revival research cycle completed
- Discovered: archive code ≠ baseline — archive has 6+ extra filters not in baseline commit e341055e
- Built `strategies/pump_fade_simple.py` — exact 190-line replica of baseline commit
- Registered pump_fade_simple in backtest/run_portfolio.py (all 5 registration points)
- Created autoresearch spec: `configs/autoresearch/pump_fade_simple_meme.json` (486 combos)
- Built `strategies/pump_fade_v4r.py` — fixed v4 archive with cooldown bug resolved
- Ran v4r autoresearch: 0/243 combos passed (correct — climax wick too rare on liquid alts)
- Diagnosed portfolio "drop" 100%→53%: NOT code break, just time window shift
- Confirmed golden portfolio intact: `portfolio_20260325_172613_new_5strat_final` (+100.93%)

**Key findings:**
- pump_fade baseline = simple 190-line code, not archive version
- VM cache only has ~11 days history → autoresearch MUST run on local machine
- Portfolio drop is not a code break; it is partly a time-window shift and partly config/pocket drift

---

## 2026-03-27 | GPT (session 10)

**Done:**
- Applied live breakout fix patch: `configs/live_breakout_v3_overlay_20260328.env`
- Server health check confirmed strategies running

---

## Before 2026-03-27 | Earlier sessions

- Initial bot setup with 5 strategies
- Golden portfolio research: +100.93%, PF=2.078, 5 strategies, 10 symbols
- DeepSeek signal audit integration
- Autoresearch pipeline established
- Equities WF gate research completed (TSLA, GOOGL, JPM, JPM validated)

---

## Quick Reference

**Server:** 64.226.73.119
**Bot dir (server):** /root/by-bot/
**Bot dir (local):** ~/Documents/Work/bot-new/bybit-bot-clean-v28/

**Golden portfolio:** `portfolio_20260325_172613_new_5strat_final`
- Return: +100.93% | PF: 2.078 | Strategies: 5 | Symbols: 10

**Current live overlay:** `live_breakout_v3_overlay_20260328.env` (applied on top of existing live5 config, 2026-03-28)

**Current allowlists:**
- ASC1: ATOMUSDT, LINKUSDT, DOTUSDT
- ARF1: LINKUSDT, LTCUSDT, SUIUSDT, DOTUSDT, ADAUSDT, BCHUSDT
- BREAKDOWN: BTCUSDT, ETHUSDT, SOLUSDT, LINKUSDT, ATOMUSDT, LTCUSDT

**Alpaca paper config:** `configs/alpaca_paper_local.env`
- Max positions: 2 | Alloc: 45% per position | Capital override: $500

**AI roles:**
- Claude: architect, research specs, diagnosis, code
- GPT: deployment, server ops, quick fixes
- DeepSeek: signal audit (live), weekly analysis (planned)
