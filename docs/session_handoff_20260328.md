# Session Handoff Report — 2026-03-28

## Update — 2026-04-01

### Server AI layer is now deployed on `/root/by-bot`

The earlier note that the AI/autonomy bundle still needed deploy is no longer true.
The following files are now present on the live server and the service was restarted successfully:

- `bot/health_gate.py`
- `bot/allowlist_watcher.py`
- `bot/deepseek_research_gate.py`
- `bot/deepseek_overlay.py`
- `bot/deepseek_autoresearch_agent.py`
- `bot/deepseek_action_executor.py`
- `bot/trade_learning_loop.py`
- `bot/family_profiles.py`
- `configs/family_profiles.json`
- `configs/approved_specs.txt` (created as empty file)
- `scripts/deepseek_weekly_cron.py`

Service state after deploy:
- `bybot.service` → `active`

Cron state after deploy:
- `0 8 * * 1 cd /root/by-bot && python3 scripts/deepseek_weekly_cron.py >> logs/deepseek_weekly.log 2>&1`
- `0 9 * * 1 cd /root/by-bot && python3 scripts/equity_curve_autopilot.py >> logs/equity_curve.log 2>&1`

Sanity checks after deploy:
- `from bot.deepseek_research_gate import gate; print(gate.status_report())` → gate enabled, 7 pre-approved specs, 0 pending proposals
- `from bot.family_profiles import profiles; print(profiles.scale("BTCUSDT","sl",1.0))` → `1.0`
- `from bot.health_gate import gate; print(gate.status_summary())` → `{}` (no active health entries yet; note this module exposes `status_summary()`, not `status_report()`)

### What the AI layer can do on server now

1. `health_gate`
- blocks or warns on entries based on `configs/strategy_health.json`
- supports `OK / WATCH / PAUSE / KILL`
- intended to sit directly in the live bot before `maybe_signal()` calls

2. `family_profiles`
- applies family-aware scaling by coin / sleeve class
- currently sanity-check returns `1.0` for `BTCUSDT` + `sl`

3. `trade_learning_loop`
- records closed-trade patterns
- prepares bounded `trade_learning` proposals instead of self-mutating live logic

4. `deepseek_research_gate` + `deepseek_weekly_cron`
- weekly audit / research gate is now live on server
- can read proposals, pre-approved specs, and research state

Important limitation:
- the newer local fixes for `equities_alpaca_intraday_bridge.py` hot-reload and `equities_midmonth_monitor.py` auto-exit condition ordering were fixed locally after review, but were not part of the minimal AI server deploy above.

### Current local research fronts (as of 2026-04-01)

Keep active / meaningful:
- `equities_monthly_v36_current_cycle_activation`
- `triple_screen_elder_v21_trend_retest_repair`
- `inplay_scalper_minute_probe_v2`
- `micro_scalper_bounce_v1_grid`
- `micro_scalper_breakout_v1_grid`

Stopped as low-value / converged:
- `triple_screen_elder_v20_quality_filter_repair`
- `equities_monthly_v37_live_cycle_gate`
- `inplay_scalper_fast5_probe_v1`
- `micro_scalper_bounce_v2_bias_probe`

Early read:
- `Alpaca v36` remains the strongest frontier
- refreshed `Elder v21` started with much healthier early rows (`net ≈ 3.75`, `PF ≈ 5.47`, `DD ≈ 0.59`) though still failing formal thresholds
- `InPlay minute v2` now trades on honest `1m` base, but early rows are negative so far

### Practical next step after this handoff

Do not launch more blind monthly sweeps.

Priority order:
1. Let the 4 active research fronts print meaningful rows
2. If `Alpaca` remains too inert as monthly-only logic, expand the new intraday watchlist layer rather than adding another monthly grid
3. If `Elder v21` improves but still misses by density/net, move to targeted `v22` instead of another giant blind sweep
4. If `InPlay minute v2` continues to trade but stays negative, keep the minute engine and repair the signal logic, not the data layer
5. Use `ALPACA_AUTO_EXIT_DRY_RUN=1` first; do not enable hard auto-exit live without a few monitor cycles

## What Was Done This Session

---

### 1. pump_fade Revival — Full Research Cycle

**Goal:** Revive the retired `pump_fade` strategy as a research-only branch, understand why the baseline worked, and prepare a proper autoresearch spec.

**What we found:**

The baseline (`pf_v4c_240d`) had a label that implied v4 (climax wick mode), but inspection of actual trade reasons showed `"pump X%/120m then reversal"` — pure BASE mode. The `v4` in the name was a git commit tag, not a strategy variant.

This was important because:
- We launched a 243-combo v4 autoresearch → 0 passing combos (correct: exhaustion wick is too rare on liquid alts)
- The archive `pump_fade.py` (1191 lines) has 6+ extra filters **not present** in the baseline commit (exhaustion filter, confirm_bars, entry_too_early, leg_pct, move_ref override, etc.)
- The actual baseline was the simple 190-line `strategies/pump_fade.py` at commit `e341055e`

**What was built:**

| File | Action |
|------|--------|
| `strategies/pump_fade_v4r.py` | Revival of archive v4 mode — cooldown bug fixed, dead code removed |
| `strategies/pump_fade_simple.py` | **Exact verbatim copy of commit e341055e** — renamed class/helpers to avoid collision |
| `backtest/run_portfolio.py` | Registered both new strategies (5-point registration each) |
| `configs/autoresearch/pump_fade_v4r_alts.json` | 243-combo v4 spec — completed, 0 passing |
| `configs/autoresearch/pump_fade_base_meme.json` | 486-combo archive BASE mode spec — superseded |
| `configs/autoresearch/pump_fade_simple_meme.json` | **✅ Correct spec** — 486 combos using pump_fade_simple on meme coins |
| `docs/pump_fade_v4r_revival_report.md` | Full diagnosis + decisions |

**Autoresearch to run (on your LOCAL machine, not VM):**
```bash
cd ~/Documents/Work/bot-new/bybit-bot-clean-v28
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/pump_fade_simple_meme.json \
  > /tmp/pf_simple_autoresearch.log 2>&1 &
echo "PID: $!"
```

> VM cache only has the last ~11 days per symbol. Full 240-day history is on your local machine.

**Deploy condition:** ≥5 combos passing, at least 1 with trades ≥15 and PF ≥1.6.

---

### 2. Portfolio "Drop" Diagnosis

The portfolio appeared to drop from ~100% to ~53%. This is NOT a code break or money loss.

- Golden portfolio: `portfolio_20260325_172613_new_5strat_final` — +100.93%, PF=2.078 (5 strategies, annual ending Feb 2026)
- Current "mirror" run ended March 2026, dropping a good March 2025 candle and adding a weaker Feb-Mar 2026 period
- Your live account balance was unchanged (~$100 as always)
- No code was broken; GPT already applied a live breakout fix patch (`live_breakout_v3_overlay_20260328.env`)

---

### 3. Dynamic Allowlist Script — `scripts/dynamic_allowlist.py`

**Goal:** Replace static hardcoded symbol lists with a live scan that adapts to market conditions weekly.

**What it does:**

1. Fetches live Bybit tickers (24h turnover, price) and instruments-info (listing age)
2. Fetches 1h ATR% for up to 120 symbols (configurable)
3. Applies per-strategy filter profiles:
   - **ASC1** (sloped channel): turnover ≥30M, ATR% 0.28–0.90%, age ≥120d, top 8
   - **ARF1** (flat fade): turnover ≥20M, ATR% 0.28–1.10%, age ≥90d, top 10
   - **BREAKDOWN**: turnover ≥50M, ATR% 0.30–3.00%, age ≥90d, top 12
4. Optional backtest performance gate — filters out symbols with bad historical PF/net
5. Outputs a dated `.env` file ready to apply

**Usage:**
```bash
# Dry run (no file written)
python3 scripts/dynamic_allowlist.py --dry-run

# Standard weekly scan
python3 scripts/dynamic_allowlist.py \
    --out-env configs/dynamic_allowlist_latest.env

# With backtest gate from recent run
python3 scripts/dynamic_allowlist.py \
    --trades-csv backtest_runs/portfolio_20260327_161054_.../trades.csv \
    --out-env configs/dynamic_allowlist_latest.env

# Apply result
python3 scripts/apply_env_overlay.py configs/dynamic_allowlist_latest.env
```

**Flags:**
- `--max-scan-symbols 120` — cap ATR fetches (higher = slower but more candidates)
- `--atr-lookback-days 14` — ATR window
- `--asc1-top-n / --arf1-top-n / --breakdown-top-n` — override top-N per family
- `--bt-min-trades / --bt-min-pf` — override backtest gate thresholds
- `--quiet` — for cron jobs

**Anchor symbols** (always kept regardless of market filter):
- ASC1: LINKUSDT, ATOMUSDT
- ARF1: LINKUSDT, LTCUSDT
- BREAKDOWN: BTCUSDT, ETHUSDT, SOLUSDT

---

## What To Do Next

### Immediate (this week)

1. **Run pump_fade_simple autoresearch on your local machine** (see command above). Takes ~2-4 hours. Check results with:
   ```bash
   tail -f /tmp/pf_simple_autoresearch.log
   # When done:
   cat backtest_runs/autoresearch_*/results.csv | head -20
   ```

2. **Run dynamic_allowlist.py for the first time** to see what the live scan produces today:
   ```bash
   cd ~/Documents/Work/bot-new/bybit-bot-clean-v28
   python3 scripts/dynamic_allowlist.py --dry-run
   ```
   Compare output against current static lists. If sensible, run without `--dry-run`.

3. **Add dynamic_allowlist.py to weekly cron** (runs Sunday nights):
   ```bash
   crontab -e
   # Add:
   0 22 * * 0 cd ~/Documents/Work/bot-new/bybit-bot-clean-v28 && python3 scripts/dynamic_allowlist.py --quiet --out-env configs/dynamic_allowlist_latest.env
   ```

### Medium-term

4. **pump_fade_simple deployment** — after autoresearch passes, add to live bot with:
   - Small risk_pct (0.3–0.5%) since it's a new strategy in production
   - Universe: top 5 passing symbols from autoresearch
   - Monitor for 30 days before increasing size

5. **Backtest-gated allowlist** — once you have a rolling 90-day backtest run, add `--trades-csv` to dynamic_allowlist.py so it also gates on recent performance.

6. **MSCALP / ASR1 allowlists** — dynamic_allowlist.py currently covers ASC1, ARF1, BREAKDOWN. Adding MSCALP and ASR1 profiles requires knowing their strategy tag names in trades.csv — straightforward to add.

### Architecture (longer term)

7. **DeepSeek integration** — DeepSeek already sits inside the live bot for signal audit. To give it stronger influence:
   - Create a `deepseek_suggest.py` that runs weekly autoresearch and posts candidate configs to a queue
   - Bot reads queue at startup and A/B-tests suggested params vs current
   - Requires safety guardrails: max risk_pct per suggestion, paper-trade only until PF ≥ 1.5 over 30 live trades

8. **Claude + GPT + DeepSeek handoff protocol** — currently manual (Markdown reports like this one). Consider a `docs/ai_handoff.json` that any AI can read to understand current state, active strategies, last backtest results, and open tasks.

---

## Current Live Bot State (as of 2026-03-28)

- **Server:** 64.226.73.119
- **Active strategies:** breakout, sloped_channel (ASC1), flat_resistance_fade (ARF1), inplay_breakdown, midterm_pullback
- **Latest env:** `live_breakout_v3_overlay_20260328.env` (applied by GPT)
- **Current allowlists:**
  - ASC1: ATOMUSDT, LINKUSDT, DOTUSDT
  - ARF1: LINKUSDT, LTCUSDT, SUIUSDT, DOTUSDT, ADAUSDT, BCHUSDT
  - BREAKDOWN: BTCUSDT, ETHUSDT, SOLUSDT, LINKUSDT, ATOMUSDT, LTCUSDT

---

## File Index (this session)

| File | Status |
|------|--------|
| `strategies/pump_fade_simple.py` | NEW — exact baseline replica |
| `strategies/pump_fade_v4r.py` | NEW — archive v4 with cooldown fix |
| `backtest/run_portfolio.py` | MODIFIED — registered both new strategies |
| `configs/autoresearch/pump_fade_simple_meme.json` | NEW — 486-combo spec, ready to run |
| `configs/autoresearch/pump_fade_v4r_alts.json` | NEW — completed, 0 passing (archived) |
| `configs/autoresearch/pump_fade_base_meme.json` | NEW — superseded by pump_fade_simple_meme |
| `scripts/dynamic_allowlist.py` | NEW — dynamic per-strategy symbol scanner |
| `docs/pump_fade_v4r_revival_report.md` | NEW — full pump_fade diagnosis |
| `docs/session_handoff_20260328.md` | NEW — this file |
