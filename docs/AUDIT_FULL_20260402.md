# Full Strategy Audit — 2026-04-02

Complete review of all active strategies: scalpers, InPlay, Elder, Alpaca.

---

## Fixes Applied This Session

### 1. `micro_scalper_v1.py` — session window (LOW → FIXED)
**Problem:** `session_end_utc = 17` cut off EU afternoon and all of NY session. The bounce and breakout variants were already at 22.
**Fix:** Changed default to `session_end_utc = 22` to match the other two scalper variants.
**Env override:** `MSCALP_SESSION_END_UTC`

### 2. `strategies/inplay_breakout.py` — no time stop in "fixed" mode (MEDIUM → FIXED)
**Problem:** In the default "fixed" exit mode, `TradeSignal` was returned without `time_stop_bars`, so the field defaulted to 0 (disabled). A trade that enters but price drifts sideways without hitting SL or TP could hang indefinitely. Runner mode had a 288-bar time stop, but fixed mode had none.
**Fix:** Added `time_stop = _env_int(f"{p}_TIME_STOP_BARS", 0)` and passed it into the TradeSignal. Default stays 0 (no change in behavior unless configured), but you can now set `BREAKOUT_TIME_STOP_BARS=96` (8h on 5m bars) or `BREAKDOWN_TIME_STOP_BARS=96`.
**Recommended:** Set `BREAKOUT_TIME_STOP_BARS=96` and `BREAKDOWN_TIME_STOP_BARS=96` in your env.

---

## Previously Fixed (Earlier Sessions)

| File | Severity | Issue |
|------|----------|-------|
| `alt_resistance_fade_v1.py` | MEDIUM | Entry price mismatch: sl/tp validated against `cur` (kline close) but entry was `float(c)` (live tick). Fix: use `entry_price = float(c)` for geometry checks. |
| `alt_inplay_breakdown_v1.py` | LOW | `TradeSignal` used in type hints but not explicitly imported. Safe due to `from __future__ import annotations` but brittle. Fix: added explicit import. |
| `micro_scalper_bounce_v1.py` | LOW | `session_end_utc=17`, RR=1.25 (below breakeven after fees), cooldown=1 bar. Fixed to 22/1.5/3. |
| `micro_scalper_breakout_v1.py` | LOW | RR=1.10, cooldown=1, time_stop=8, session_end=17. Fixed to 1.5/3/20/22. |
| `configs/autoresearch/inplay_scalper_minute_probe_v2.json` | MEDIUM | BREAKOUT_RR range was [0.7, 0.9] — sub-breakeven. Fixed to [1.2, 1.5, 1.8]. |
| `configs/autoresearch/triple_screen_elder_v21_trend_retest_repair.json` | MEDIUM | Shorts-only Elder strategy tested on bull market period → 0 wins. Fixed: added TS132_ALLOW_LONGS, bearish date range. |

---

## Remaining Known Issues (Not Fixed)

### 3. VWAP boundary misalignment — all micro_scalper variants (LOW)
**Problem:** The micro scalper uses a VWAP anchor that resets at UTC midnight (00:00), but Bybit's settlement and daily funding reset is at 08:00 UTC. This creates an 8-hour drift where the VWAP anchor doesn't match the "true" daily open from the market's perspective.
**Impact:** Moderate — in practice most liquid moves happen during London/NY overlap (7–17 UTC) where both anchors have converged. Worst distortion is in the 00:00–08:00 UTC window.
**Recommended fix:** Pass `vwap_reset_hour=8` (or make it env-configurable) so the anchor aligns with Bybit settlement. Not done yet — requires testing.

### 4. `triple_screen_v132` — BTC filter silently kills all trading (LOW)
**Problem:** If `TS132_USE_BTC_FILTER=1` is set, the strategy returns `None` for every tick with no log warning (line 297–298: `if self.cfg.use_btc_filter: return None`). This is because there's no cross-symbol feed in the current engine. The comment says "not supported" but a silent failure is dangerous.
**Default:** `False`, so safe unless explicitly enabled.
**Recommended:** Add a startup warning log: `log_error("[TS132] use_btc_filter=True is not supported — all signals suppressed")`.

---

## No Issues Found

### `triple_screen_v132.py` (Elder) — archive but still active
- Logic: trend screen on hourly EMA45, oscillator (stoch/rsi/cci) on entry TF → signal when trend aligns and oscillator crosses oversold/overbought threshold
- RR: `tp_atr_mult=9.0` / `sl_atr_mult=2.0` → RR=4.5 ✅ (very healthy)
- Trailing stop: activates after 3 ATR gain for longs, 4 ATR for shorts — reasonable
- Time stop: 576 bars (48h in 5m bars) — fine for swing
- `allow_longs=True`, `allow_shorts=True` by default ✅
- Mode logic: conservative/active/aggressive correctly implement crossover thresholds
- **Note:** Strategy warms up from live ticks (not klines). After bot restart, ~30+ ticks needed before signals resume. This is expected.

### `equities_monthly_research_sim.py`
- Entry at open of next bar after month-end snapshot ✅
- Stop: `entry_bar.o - stop_atr_mult * atr20` (default mult=1.5) — always below entry ✅
- Target: `entry_bar.o + target_atr_mult * atr20` (default mult=2.5) → RR≈1.67 ✅
- Longs only (correct for monthly momentum strategy)
- Earnings blackout, regime breadth filters, correlation penalty all correctly implemented
- Universe health score formula sensible (rewards persistent strength, punishes volatility)

### `alt_resistance_fade_v1.py` (after previous fix)
- Entry/SL/TP geometry now consistent — all validated against live tick price ✅
- Regime filter (weak/sideways 4H EMA) correct ✅
- Cooldown and time stop present ✅

### `alt_inplay_breakdown_v1.py`
- Properly wraps InPlayBreakoutWrapper with `env_prefix="BREAKDOWN"` ✅
- Import fix applied ✅

---

## Deployment Notes

Files changed this session (need to sync to server):
- `strategies/micro_scalper_v1.py` — session_end_utc fix
- `strategies/inplay_breakout.py` — fixed-mode time stop

Suggested deploy command (from project root):
```bash
rsync -avz --checksum -e "ssh -i ~/.ssh/by-bot" \
  strategies/micro_scalper_v1.py \
  strategies/inplay_breakout.py \
  root@64.226.73.119:/root/by-bot/strategies/
systemctl restart bybot
```

Recommended env additions after deploy:
```bash
# Give InPlay fixed-mode trades an 8-hour max hold
BREAKOUT_TIME_STOP_BARS=96
BREAKDOWN_TIME_STOP_BARS=96
```

---

## Summary: Strategy Health by Category

| Strategy | Status | Notes |
|----------|--------|-------|
| `micro_scalper_v1` | ✅ Fixed | Session window extended to 22 UTC |
| `micro_scalper_bounce_v1` | ✅ Fixed | Session/RR/cooldown fixed in prior session |
| `micro_scalper_breakout_v1` | ✅ Fixed | RR/cooldown/time_stop fixed in prior session |
| `inplay_breakout` (longs) | ✅ Fixed | Time stop now configurable in fixed mode |
| `alt_inplay_breakdown_v1` (shorts) | ✅ Fixed | Import + same time stop fix via wrapper |
| `alt_resistance_fade_v1` | ✅ Fixed | Entry price geometry corrected |
| `triple_screen_v132` (Elder) | ⚠️ Minor | BTC filter silently kills trading if enabled; otherwise clean |
| `equities_monthly_research_sim` | ✅ Clean | No logic issues found |
| VWAP anchor (all scalpers) | ⚠️ Known | 8h drift vs Bybit settlement — low priority |
