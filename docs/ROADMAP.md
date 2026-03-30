# Project Roadmap — Trading Bot

> Last updated: 2026-03-30 | Author: Claude + GPT
> Living document — update after each major session.

---

## Vision

A self-improving, multi-market trading system where three AIs (Claude, GPT, DeepSeek) have
clearly defined roles, each part of the bot adapts dynamically to market conditions, and the
human owner spends minimal time on maintenance while retaining full control over capital decisions.

**Two income streams:**
- Bybit perpetual futures (crypto) — active, 5–8 intraday strategies
- Alpaca paper → live (US equities) — monthly rotation + intraday validated combos

**Three AI roles:**
- **Claude** — architecture, research specs, code, diagnosis
- **GPT** — deployment, ops, quick patches, server management
- **DeepSeek** — live signal audit, weekly param tuning, universe expansion, autonomous research proposals

---

## DeepSeek Autonomy Architecture

DeepSeek is already deeply integrated (3 modules, Telegram commands, approval queue).
What exists vs. what's needed to reach full autonomy:

| Capability | Status |
|-----------|--------|
| Signal audit (per-trade sanity check) | ✅ Live on server |
| `/ai_tune <strategy>` manual analysis | ✅ Works via Telegram |
| Approval queue + `/ai_approve` safe deploy | ✅ Works |
| `/ai_rollback` env revert | ✅ Works |
| Automated weekly sweep (all strategies) | ✅ Built and active on server |
| Universe expansion (new symbols suggestions) | ✅ Built and weekly `dynamic_allowlist` advisory cron active |
| Autoresearch result scanner | ✅ Built → weekly cron phase 3 |
| New strategy research (propose spec files) | ⚠️ Partial — advisory only |
| Auto-trigger autoresearch based on analysis | ❌ Future — P2/P3 |
| Cross-strategy correlation analysis | ❌ Future — P3 |
| Auto-apply live parameter changes | ❌ Intentionally disabled — approval required |

**Current server cadence:**
```bash
# Already active on server:
30 21 * * 0 /bin/bash -lc 'cd /root/by-bot && source .venv/bin/activate && \
  python3 scripts/dynamic_allowlist.py --quiet --out-env configs/dynamic_allowlist_latest.env \
  >> /root/by-bot/logs/dynamic_allowlist.log 2>&1'

0 22 * * 0 /bin/bash -lc 'cd /root/by-bot && source .venv/bin/activate && \
  python3 scripts/deepseek_weekly_cron.py --quiet >> /root/by-bot/logs/deepseek_weekly.log 2>&1'
```

**Reality check:** this is protective autonomy, not full autonomy yet.
- `dynamic_allowlist` now refreshes a weekly symbol candidate file on the server, but does **not** auto-apply it to live.
- `deepseek_weekly_cron.py` now sends/records weekly analysis and queues proposals, but those proposals still require `/ai_approve`.
- This reduces regime drift risk and maintenance burden; it does **not** guarantee the bot cannot degrade.

**Phases run each Sunday:**
1. `audit` — health check of recent runs (PF, DD trend per strategy)
2. `tune` — DeepSeek proposes param changes for each strategy → approval queue
3. `research` — flags finished autoresearch with PASS combos
4. `universe` — DeepSeek suggests new symbols to test per strategy family
5. `report` — full digest sent to Telegram

**Human interaction remains minimal** — you only:
- Read Sunday Telegram digest
- `/ai_approve <id>` or `/ai_reject <id>` for param changes
- Manually decide to deploy after reviewing

---

## Current State (March 2026)

### Crypto (Bybit) ✅ Working
| Component | Status |
|-----------|--------|
| 5 live strategies (breakout, ASC1, ARF1, BREAKDOWN, midterm) | ✅ Live |
| Golden portfolio backtest +100.93% | ✅ Baseline locked |
| Strongest reproducible candidate `v5` | ✅ Promoted to live (`~+94.8% / +89.7%` annual validations) |
| dynamic_allowlist.py (weekly symbol refresh) | ✅ Built and active as weekly advisory cron |
| pump_fade_simple (baseline replica) | ✅ Built, autoresearch pending |
| pump_fade_v4r (archive revival) | ✅ Built, 0 combos pass (archived) |
| DeepSeek signal audit + trade review | ✅ Live |
| DeepSeek weekly research cron | ✅ Active on server |
| Equity-curve autopilot for crypto sleeves | ⚠️ Script exists, not yet wired into live entry gating |
| Regime detector / capital allocator | ❌ Not built yet |

### Alpaca (Equities) ⚠️ Paper, needs fixes
| Component | Status |
|-----------|--------|
| Monthly momentum picker | ⚠️ 1 trade only — hit stop (XOM -3.79% March 2026) |
| WF-validated intraday strategies | ✅ Backtested (TSLA/GOOGL/JPM) |
| Regime filter (SPY SMA gate) | ⚠️ Exists in research/intraday code, not yet proven in paper workflow |
| Bridge WF intraday → paper execution | ⚠️ Script exists, not yet safely armed on server |
| Daily loss / equity-curve filters for intraday | ⚠️ Scripted, not yet production-armed |

---

## Alpaca Diagnosis

**Root cause of red months:** The monthly momentum strategy picks stocks at month-end
and enters at month-start. March 2026 was a macro risk-off month (tariff fears, SPY sold off).
XOM bought March 2 → stopped out same day at -3.79%. Zero regime awareness.

**What walkforward testing already proved works:**

| Strategy | Symbol | WF Segments | Both+ | Net (cents) |
|----------|--------|-------------|-------|-------------|
| breakout_continuation + quality_guard | TSLA | 15 | 10/15 (67%) | +6200 |
| grid_reversion + safe_winrate | GOOGL | 15 | 10/15 (67%) | +2270 |
| grid_reversion | JPM | 15 | 10/15 (67%) | +1542 |
| trend_retest + quality_guard | AAPL | 15 | 9/15 (60%) | +1349 |

These intraday strategies are **already validated** but not yet connected to live execution.
The fix is to bridge them — not to rebuild the monthly strategy from scratch.

---

## Priority Queue

### 🔴 P0 — Do This Week

**0. Keep the live bot on the strongest verified stack**
- `v5` is now the live full-stack overlay.
- Do not replace it with new sleeves unless they beat `v5` in apples-to-apples annual compare.
- Treat `v5` as the new operational baseline until disproven.

**0b. Do not let Elder absorb the whole week**
- Current best Elder insight is useful, but not enough for live.
- Decision rule:
  - if `v15` finishes with repeated `4` negative-month rows, continue into `v16`
  - if `v15` falls back to `5-6` negative months, freeze Elder and redirect attention to the next sleeve
- This prevents the project from stalling on one half-working strategy.

**1. Run pump_fade_simple autoresearch locally**
```bash
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/pump_fade_simple_meme.json \
  > /tmp/pf_simple.log 2>&1 &
```
Expected runtime: 2–4 hours. Goal: ≥5 combos with PF ≥1.5 and trades ≥15.

**2. Turn weekly autonomy into a closed advisory loop**
- Weekly `dynamic_allowlist` cron is active — inspect `configs/dynamic_allowlist_latest.env` after Sundays.
- Weekly `DeepSeek` cron is active — inspect `logs/deepseek_weekly.log` and `/ai_pending`.
- Next missing step is not “more cron”, but a clean review workflow:
  - Sunday: auto-generate candidate allowlist and AI proposals
  - Monday: review diff vs current live
  - apply only if annual compare / bounded backtest agrees

**2b. Prepare the autonomy bundle for safe server deployment**
- Local files now exist:
  - `bot/health_gate.py`
  - `bot/allowlist_watcher.py`
  - `bot/deepseek_research_gate.py`
  - `bot/family_profiles.py`
- Next engineering task is a clean deploy bundle + smoke verification on server.
- Goal: move from "advisor autonomy exists locally" to "bounded autonomy is actually live".

**3. Fix equities autoresearch parser path**
`equities_monthly_v23_spy_regime_gate` did not fail strategically; the generic wrapper failed to parse the equities summary format.
- Repair the shared wrapper or add a dedicated equities-autoresearch path.
- Only then judge whether `SPY/QQQ` regime gate really improves red months.

**4. Test SPY regime filter for Alpaca monthly strategy**
One-line logic in `equities_monthly_research_sim.py`:
only enter longs when SPY close > SPY 50-day SMA.
If SPY below 50 SMA → stay flat, don't buy picks that month.
This would likely have avoided that specific March 2026 entry; it is a first repair, not the full solution.

---

### 🟡 P1 — This Month

**5. Connect WF-validated intraday strategies to Alpaca paper ✅ DONE**
`scripts/equities_alpaca_intraday_bridge.py` — built with 3-layer protection:
- L1: SPY regime gate (SMA50 — today correctly blocked entries, SPY $670 < SMA50 $687)
- L2: Daily loss limit (2% of equity)
- L3: Equity curve filter (20d rolling P&L)
Run daily dry-run, observe Telegram signals → switch to `--live` after 2+ weeks.

**5b. Alpaca v30 — regime-adaptive concentration instead of naive diversification**
`v29` showed that simply forcing `TOP_N=3/4` does not beat the strong `TOP_N=2` frontier.
The next repair direction is therefore smarter portfolio logic, not "just more names":
- keep concentration tight in weak / risk-off conditions
- allow broader selection only in stronger benchmark/breadth regimes
- prefer smoother worst-month profile over squeezing a few extra raw return points
- test this as a bounded research branch before touching paper/live

**6. Elder Triple Screen revival — 6th strategy candidate**
`triple_screen_v132.py` (archive) is still the active Elder core, but the branch has been narrowed substantially.
What we learned:
- old symmetric long+short `v13/v14` paths were too noisy by month
- `v15` short-bias reduces negative months, but loses density
- strict canonical `v17` repair is too dry unless we re-open it carefully
Current next steps:
- finish `v15`
- if smoother months hold, run `v16`
- only after a real isolated PASS should we re-open the 6-strategy portfolio compare

**6b. Trend + trailing family evaluation**
We already have trend/trailing behavior in the codebase, but not yet as a proven live upgrade:
- `TS132 / Elder` is the clearest dedicated trend-following + trailing candidate
- `alt_sloped_channel_v1` also supports trailing logic in code, but current live `v5` keeps that trail disabled
- next step is to compare "strict trend-following with trail" against the current mean-reverting/sloped mix, not to assume trailing is automatically better

**7. Deploy pump_fade_simple to live (after autoresearch)**
- Start at risk_pct = 0.3% (very small)
- Top 5 symbols from passing combos
- Monitor 30 days before increasing size

**8. Wire equity autopilot into live entry gates**
- `scripts/equity_curve_autopilot.py` writes `configs/strategy_health.json`
- Main bot still does NOT read it before entries
- Next: add health check hook in main trading loop
  - `WATCH` = advisory + Telegram only
  - `PAUSE/KILL` = block new entries for that strategy family

---

### 🟢 P2 — Next Month

**9. Dual-AI architecture: Claude as monthly strategic analyst**
`scripts/claude_monthly_analyst.py` — skeleton ready, awaiting API key.
Activate when bot P&L consistently > $200/month.

Role split:
| Task | AI | Frequency | Est. cost |
|---|---|---|---|
| Param tuning, signal audit | DeepSeek | Weekly | ~$2/month |
| Universe expansion | DeepSeek | Weekly | included |
| Portfolio health analysis | Claude Sonnet | Monthly | ~$5/month |
| New strategy design | Claude Sonnet | On demand | ~$0.50/call |
| Deep code review | Claude Opus | Quarterly | ~$3/call |

Usage when active:
```bash
python3 scripts/claude_monthly_analyst.py --report
python3 scripts/claude_monthly_analyst.py --strategy-idea "funding rate reversion"
python3 scripts/claude_monthly_analyst.py --diagnose alt_resistance_fade_v1
```

**10. New strategy: Funding Rate Reversion (Bybit-specific)**
Bybit pays/receives funding every 8h. When |funding_rate| > 0.08% → market is overextended.
Edge: counter-trend entry after extreme funding → mean reversion within 1-3 candles.
Uncorrelated with existing 5 strategies (different signal source).
Implement: `strategies/funding_rate_reversion_v1.py` + autoresearch spec.

**11. DeepSeek weekly cron — move from advisory to bounded research operator**
- already active on server
- next step: let it launch only pre-approved bounded research jobs, not arbitrary tune ideas
- keep live changes behind approval
- desired flow: `observe -> propose -> run bounded compare -> queue diff -> approve`

**9. Alpaca equity universe expansion**
Current: 10 stocks (AAPL, AMD, AMZN, GOOGL, JPM, META, MSFT, NVDA, TSLA, XOM)
Add: sector ETFs (XLK, XLF, XLE, QQQ, IWM) for regime monitoring.
Use `scripts/equities_universe_refresh.py` as base.

**10. Backtest-gated allowlist on the server**
The current weekly server cron generates a market-driven candidate.
The stronger long-term version is:
- refresh latest golden trades/per-strategy attribution on server
- run `dynamic_allowlist.py` with backtest gate
- compare candidate vs current live pockets before applying

**11. Portfolio-level risk monitor**
When daily PnL < -3% of account: automatically halve position sizes for the next 24h.
When 3 consecutive losing days: send Telegram alert + pause new entries until manual review.

**12. Regime detector + allocator**
- start simple: ADX/ATR/range-compression regime classes
- map sleeves to regimes (`breakout/sloped` in trend, `flat` in range, reduced risk in transition)
- only later escalate to HMM/GMM if the simple regime layer proves useful

**12c. Reuse winning structure across strategies**
- This is now a real design principle, not a side note:
  - side asymmetry from `breakdown` → Elder short-bias
  - symbol pockets from `v5` → family-restricted research, not full-market sweeps
  - bounded compares before live → mandatory for every candidate sleeve
- Use this as the default design pattern for future repairs and new sleeves.

**12b. Breakout weak-chop adaptation**
- live diagnostics show `impulse_weak` dominates breakout no-signal reasons in quieter sessions
- treat this as a bounded research problem, not a panic live tweak
- test a softer breakout profile only if annual quality survives
- if quality collapses, leave breakout strict and solve the gap later with the regime allocator

---

### 🔵 P3 — Quarter

**13. Funding rate capture strategy**
Long spot + short perp on high-funding coins.
Expected: ~4–6% annualized, near-zero directional risk.
Requires separate risk bucket and capital allocation.

**14. Volatility compression breakout (4h)**
After ATR contracts below 30-day average → trade breakout of the range.
Works on different symbols than 5m breakout, fewer signals but higher R:R.

**15. Full AI handoff protocol**
File: `docs/ai_handoff.json` — machine-readable state:
- Active strategies and their current configs
- Last backtest results (PF, trades, date)
- Open tasks with priority
- Known issues / anomalies
Any AI reads this at session start instead of needing Markdown summaries.

**16. Telegram morning report bot**
Daily at 07:00 UTC:
- PnL last 24h (crypto + equity separately)
- Active positions
- Flags: strategy with 3+ consecutive losses, allowlist staleness
- DeepSeek weekly summary if available

**17. Split-brain optimizer stack**
- LLMs propose structure and bounded hypotheses
- numeric optimizer / autoresearch finds the numbers
- archive only parameter islands that survive rolling windows
- this is the right path to “self-improving” without letting any one model freewheel the live bot

---

## Architecture Blueprint (12-month target)

```
┌─────────────────────────────────────────────────┐
│                  YOU (owner)                     │
│  Weekly: read Telegram digest, approve changes   │
└──────────────────┬──────────────────────────────┘
                   │
      ┌────────────▼─────────────┐
      │        AI Team           │
      │  Claude   → architecture │
      │  GPT      → ops/deploy   │
      │  DeepSeek → optimization │
      └────────────┬─────────────┘
                   │
      ┌────────────▼───────────────────────────────┐
      │          Weekly Cycle (automated)           │
      │  Sun:  dynamic_allowlist → new .env         │
      │        deepseek_weekly_report → analysis    │
      │        health_check → flag anomalies        │
      │  Mon:  Telegram digest to you               │
      └────────┬───────────────────────────────────┘
               │
      ┌─────────▼────────────────────────────────────┐
      │             Execution Layer                   │
      │                                               │
      │  Bybit (server 64.226.73.119)               │
      │  ├── breakout        (15–20 symbols)         │
      │  ├── ASC1            (8 symbols, dynamic)    │
      │  ├── ARF1            (10 symbols, dynamic)   │
      │  ├── BREAKDOWN       (12 symbols, dynamic)   │
      │  ├── midterm         (BTC/ETH)               │
      │  └── pump_fade_simple (5–8 meme coins) [NEW] │
      │                                               │
      │  Alpaca (paper → live)                       │
      │  ├── Monthly picks + SPY regime gate [FIX]   │
      │  ├── TSLA breakout_continuation (intra) [NEW]│
      │  ├── GOOGL grid_reversion (intra) [NEW]      │
      │  └── JPM  grid_reversion (intra) [NEW]       │
      │                                               │
      │  Passive                                      │
      │  └── Funding rate capture [FUTURE]            │
      └───────────────────────────────────────────────┘
```

---

## Key Metrics to Track

| Metric | Target | Current |
|--------|--------|---------|
| Crypto annual return | > +80% | +100.93% (golden portfolio) |
| Crypto max drawdown | < 15% | ~8% |
| Crypto profit factor | > 1.8 | 2.078 |
| Alpaca monthly win rate | > 55% | 0% (1 trade only) |
| Dynamic allowlist freshness | < 7 days | Not yet running |
| DeepSeek weekly reports | weekly | Not yet |
| pump_fade_simple (after deploy) | PF > 1.5 | Pending autoresearch |

---

## File Index

| File | Purpose |
|------|---------|
| `strategies/pump_fade_simple.py` | Baseline pump/fade strategy (exact replica) |
| `strategies/pump_fade_v4r.py` | Archive v4 revival (0 combos, archived) |
| `scripts/dynamic_allowlist.py` | Weekly symbol scanner, per-strategy profiles |
| `scripts/universe_scan.py` | Base market scanner |
| `scripts/build_breakout_allowlist.py` | Backtest-performance-based allowlist builder |
| `scripts/equities_alpaca_paper_bridge.py` | Monthly picks executor (Alpaca) |
| `scripts/equities_monthly_research_sim.py` | Monthly backtest simulator |
| `configs/autoresearch/pump_fade_simple_meme.json` | 486-combo autoresearch spec |
| `configs/alpaca_paper_local.env` | Alpaca paper trading config |
| `docs/pump_fade_v4r_revival_report.md` | Full pump_fade diagnosis |
| `docs/session_handoff_20260328.md` | Latest session summary |
| `docs/ROADMAP.md` | This file |
| `docs/JOURNAL.md` | Session-by-session work log |
