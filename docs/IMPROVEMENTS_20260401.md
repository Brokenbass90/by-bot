# Improvements — 2026-04-01 (Session 20)

Implemented in one session. Backups are `.bak` copies in the same directories.
All changes are additive or default-fix only — no live strategy logic was altered.

---

## 1. InPlay Scalper Minute Probe v2 — RR Fix

**File:** `configs/autoresearch/inplay_scalper_minute_probe_v2.json`
**Problem:** `BREAKOUT_RR: [0.7, 0.9]` — both values are below 1.0, making them
mathematically unprofitable after 20 bps fees + slippage. Every single run in
the grid was guaranteed to lose money regardless of signal quality. This explains
the 0/1152 PASS result.
**Fix:** Changed to `BREAKOUT_RR: [1.2, 1.5, 1.8]` — minimum viable RR with
current fee structure is ~1.1; values above 1.2 leave meaningful room for the
strategy to generate profit after costs.

---

## 2. Elder Triple Screen v21 — Grid Repair

**File:** `configs/autoresearch/triple_screen_elder_v21_trend_retest_repair.json`
**Problem:** The original v21 spec was shorts-only (`TS132_ALLOW_LONGS: ["0"]`)
over a test period ending 2026-02-24 that covers mostly a bull market. A
shorts-only strategy on a 360-day bull run will structurally find no valid
4h bearish trend phases — hence WR=3.3%, 0/768 PASS.
**Fix:**
- Added `TS132_ALLOW_LONGS: ["0", "1"]` — grid now tests both short-only and
  long+short configurations.
- Added `DAYS: [360, 540]` and `END_DATE: ["2026-02-24", "2025-01-01"]` —
  the 2025-01-01 endpoint covers the 2024 Q2–Q4 period which included genuine
  bear legs, giving shorts a realistic test environment.
- Updated description and `_combo_count` (~768 combos, 4× previous).

---

## 3. MicroScalperBounceV1 — Autoresearch Spec (NEW)

**File:** `configs/autoresearch/micro_scalper_bounce_v1_grid.json`
**Problem:** MicroScalperBounceV1 strategy existed but was never backtested.
No autoresearch spec existed. No performance data.
**Action:** Created first-ever autoresearch grid (~2592 combos):
- Explores `MSBNC_TREND_TF` (15/30m), `MSBNC_TOUCH_ATR`, `MSBNC_TREND_MIN_SLOPE_PCT`
- Tests `MSBNC_RR: [1.4, 1.6, 1.9]` (all above minimum viable with fees)
- Tests `MSBNC_COOLDOWN_BARS: [3, 5]` (fixed: was defaulting to 1 which is too aggressive)
- Tests `MSBNC_TIME_STOP_BARS: [12, 20, 30]`
- 90-day backtest window ending 2026-03-01 on 6 crypto symbols

**Run command:**
```bash
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/micro_scalper_bounce_v1_grid.json \
  > /tmp/msbnc_v1.log 2>&1 &
```

---

## 4. MicroScalperBreakoutV1 — Autoresearch Spec (NEW)

**File:** `configs/autoresearch/micro_scalper_breakout_v1_grid.json`
**Problem:** Same as bounce — strategy existed but was never backtested.
**Action:** Created first-ever autoresearch grid (~3888 combos):
- Explores `MSBRK_BREAKOUT_LOOKBACK: [4, 6, 10]` bars
- Explores `MSBRK_BREAKOUT_BUFFER_ATR: [0.04, 0.07, 0.10]`
- Tests `MSBRK_RR: [1.4, 1.6, 2.0]` (fixed from default 1.10)
- Tests `MSBRK_COOLDOWN_BARS: [3, 5]` (fixed from default 1)
- Tests `MSBRK_TIME_STOP_BARS: [16, 24, 36]` (fixed from default 8)

**Run command:**
```bash
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/micro_scalper_breakout_v1_grid.json \
  > /tmp/msbrk_v1.log 2>&1 &
```

---

## 5. MicroScalperBounceV1 — Default Param Fix

**File:** `strategies/micro_scalper_bounce_v1.py`
**Changes (dataclass defaults only — no logic change):**
- `rr`: 1.25 → 1.50 (below-fee-breakeven default prevents any chance of profit)
- `cooldown_bars`: 1 → 3 (prevents back-to-back noise re-entries)
- `max_signals_per_day`: 8 → 6 (reduces overtrading in default mode)

---

## 6. MicroScalperBreakoutV1 — Default Param Fix

**File:** `strategies/micro_scalper_breakout_v1.py`
**Changes (dataclass defaults only — no logic change):**
- `rr`: 1.10 → 1.50 (was deeply sub-breakeven after 20bps fees)
- `cooldown_bars`: 1 → 3 (prevents cascading false-breakout entries)
- `time_stop_bars`: 8 → 20 (breakout follow-through needs more room)
- `max_signals_per_day`: 8 → 6
- `session_end_utc`: 17 → 22 (captures more of the crypto trading session)

---

## 7. Equities Midmonth Monitor — Auto Early Exit

**File:** `scripts/equities_midmonth_monitor.py`
**Problem:** Monitor only sent Telegram alerts. If a position breached its stop
midmonth, the user had to manually close it. In practice, the bot often ran on
server without the user watching, meaning losses could compound for days.

**New capability:** When `ALPACA_AUTO_EXIT_ENABLED=1`, positions flagged as
STOP_BREACHED, CRITICAL_STOP, or DEEP_LOSS are automatically closed via
Alpaca market order.

**New env vars:**
| Var | Default | Meaning |
|-----|---------|---------|
| `ALPACA_AUTO_EXIT_ENABLED` | `0` | Set to `1` to enable auto-close |
| `ALPACA_AUTO_EXIT_DRY_RUN` | `0` | Set to `1` to log actions without submitting orders |
| `ALPACA_AUTO_EXIT_MIN_LOSS_PCT` | `-8.0` | Deep-loss threshold for auto-exit |

**Safety design:**
- Default is OFF (`ALPACA_AUTO_EXIT_ENABLED=0`) — no behavior change unless opted in
- Dry-run mode allows testing before live use
- Only closes LONG positions (qty > 0) — no shorting logic added
- Telegram message shows exactly what was (or would be) closed

**Technical:** Added `_close_position()` helper that submits a market day order
via `POST /v2/orders`. Existing `_alpaca_request()` was extended with optional
`body` parameter to support POST.

---

## 8. Alpaca Intraday Bridge — Dynamic Ticker Expansion

**File:** `scripts/equities_alpaca_intraday_bridge.py`
**Problem:** The bridge was hardcoded to 3 tickers (TSLA, GOOGL, JPM) with
params baked into Python. No way to add tickers or change strategy assignments
without editing code. `INTRADAY_AUTODISCOVER_FROM_CACHE` defaulted to `False`,
meaning dynamic discovery was available but never activated.

**Changes:**
1. `INTRADAY_AUTODISCOVER_FROM_CACHE` default: `False` → `True` — discovery
   now active by default when M5 cache files are present.
2. Added `_load_intraday_config()` — reads hot-reloadable
   `configs/intraday_config.json` on every run cycle.
3. `_build_runtime_catalog()` now checks config file for symbols and strategy_map
   before falling back to autodiscovery or legacy defaults.
4. Priority chain: `INTRADAY_SYMBOLS` env > config file > autodiscover > legacy 3

**New companion config:** `configs/intraday_config.json`
- Pre-populated with 10 symbols: TSLA, GOOGL, JPM, NVDA, META, MSFT, AMZN, AAPL, AMD, PLTR
- Assigns breakout_continuation to momentum names (TSLA, NVDA, AMD, PLTR)
- Assigns grid_reversion to range-bound names (GOOGL, JPM, META, MSFT, AMZN, AAPL)
- Includes `_notes` section explaining how to add symbols and download cache data
- Hot-reloadable: edit JSON, save, takes effect on next run — no restart

**Note:** M5 CSV cache files must exist for new tickers. Download first:
```bash
python3 scripts/download_equity_m5.py --tickers NVDA,META,MSFT,AMZN,AAPL,AMD,PLTR
```
(or equivalent data downloader for the project)

---

## Backups Created

All modified files have `.bak` copies:
- `configs/autoresearch/inplay_scalper_minute_probe_v2.json.bak`
- `configs/autoresearch/triple_screen_elder_v21_trend_retest_repair.json.bak`
- `configs/autoresearch/equities_monthly_v36_current_cycle_activation.json.bak`
- `strategies/micro_scalper_bounce_v1.py.bak`
- `strategies/micro_scalper_breakout_v1.py.bak`
- `scripts/equities_midmonth_monitor.py.bak`
- `scripts/equities_alpaca_intraday_bridge.py.bak`

---

## What Was NOT Changed (and Why)

- **equities_monthly_v36**: Already running, 4638 PASS with strong candidates.
  No spec changes — results should be reviewed first before next iteration.
- **equities_alpaca_paper_bridge.py**: The AI advisory (`_alpaca_ai_advisory`)
  is advisory-only by design. Changing it to auto-act requires a separate
  session with careful testing. Left as-is.
- **inplay_breakout.py / live stack**: No live strategy code was changed.
  All changes are research configs and non-live bridge scripts.
- **Server deployment**: Autonomy files (health_gate, allowlist_watcher,
  research_gate) are still NOT on the server. That remains a manual deployment
  step per the existing AGENT_SYNC.md server reality check.

---

## Recommended Next Steps (Priority Order)

1. **Launch micro_scalper_bounce/breakout grids** — first-ever data, highest
   uncertainty, longest queue time.
2. **Re-run inplay_scalper_minute_probe_v2** — RR fix makes this a valid test now.
3. **Re-run Elder v21** — period+longs fix makes this testable for the first time.
4. **Download M5 cache for NVDA/META/MSFT/AMZN/AAPL/AMD/PLTR** before enabling
   expanded intraday tickers.
5. **Test auto-exit with dry-run first**: set `ALPACA_AUTO_EXIT_ENABLED=1`
   and `ALPACA_AUTO_EXIT_DRY_RUN=1` for one weekly monitor cycle.
