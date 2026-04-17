# Codex Task — Alpaca Paper Launch (2026-04-17)

## Goal
Launch both Alpaca paper trading branches on the server and verify they're working.

---

## CRITICAL FIX FIRST (do this before anything else)

`configs/alpaca_paper_local.env` is gitignored (has API keys) so the fix wasn't committed.
You must add `ALPACA_FRACTIONAL_SHARES=1` to the server's local.env manually:

```bash
# On server:
cd /root/by-bot
grep -q "ALPACA_FRACTIONAL_SHARES" configs/alpaca_paper_local.env || \
    echo "ALPACA_FRACTIONAL_SHARES=1" >> configs/alpaca_paper_local.env
echo "Added ALPACA_FRACTIONAL_SHARES=1"
grep "ALPACA_FRACTIONAL_SHARES" configs/alpaca_paper_local.env
```

**Why this matters:** Without it, high-price stocks (NVDA ~$880, AMZN ~$180) 
get qty=1 share instead of fractional. NVDA with $150 notional → $880 order →
completely wrong sizing or order rejection.

---

## Deploy Steps

### 1. Git pull
```bash
cd /root/by-bot
git pull origin $(git rev-parse --abbrev-ref HEAD)
```

### 2. Apply fractional shares fix (see above)

### 3. Launch both Alpaca branches
```bash
chmod +x scripts/alpaca_paper_launch_both.sh
bash scripts/alpaca_paper_launch_both.sh
```

This script:
- Syntax checks both bridges
- Runs monthly dry-run (shows current picks)
- Runs intraday dry-run (checks signals + SPY gate)
- Sets up intraday cron: every 5 min, Mon-Fri 14:00-21:00 UTC
- Sets up monthly cron: 1st of month at 09:30 UTC
- Sends Telegram launch confirmation

### 4. Verify crontab
```bash
crontab -l | grep alpaca
```

Expected:
```
*/5 14-21 * * 1-5  .../run_equities_alpaca_intraday_dynamic_v1.sh --once
30 9 1 * *          .../run_equities_alpaca_monthly_autopilot.sh
30 16 * * 1-5       .../equities_alpaca_tg_report.py
```

### 5. Run setup_server_crons.sh (adds daily digest cron)
```bash
bash scripts/setup_server_crons.sh
```

This adds:
- `#14: tg_daily_digest.py` at 08:00 UTC every day
- `#15: alpaca_monthly_autopilot` at 09:30 UTC on 1st

---

## What's New (ef74106)

### scripts/alpaca_paper_launch_both.sh (NEW)
One-command server deploy for both Alpaca branches. Replaces having to run
setup_cron_alpaca.sh + setup_cron_alpaca_intraday_dynamic_v1.sh separately.

### scripts/tg_daily_digest.py (NEW)
Morning health report (08:00 UTC). Shows:
- Bybit bot: CB state, regime, allocator, trades
- Alpaca intraday: today P&L, open positions, protection state
- Alpaca monthly: current picks, unrealized P&L via Alpaca API

### smart_pump_reversal_bot.py — VOLADJ (NEW)
Volatility-adjusted position sizing:
- Reads BTC 4h ATR% from `runtime/geometry/geometry_state.json`
- If ATR% ≥ 3.0%: positions × 0.60
- If ATR% ≥ 5.0%: positions × 0.30
- Default thresholds: VOLADJ_ATR_THRESHOLD_PCT=3.0, VOLADJ_ATR_EXTREME_PCT=5.0
- No API calls — reads cached geometry file (updated hourly by cron)
- Hot-reloadable via env vars: VOLADJ_ENABLED, VOLADJ_HIGH_MULT etc.
- Disable with: VOLADJ_ENABLED=0

### strategies/alt_slope_break_v1.py + alt_horizontal_break_v1.py
`macro_require_bullish` default changed `False → True`.
Now longs ALWAYS require 4h MACD hist > 0, even when ALLOW_LONGS=1.
This means:
- Bear market (current): MACD hist < 0 → longs blocked even if ALLOW_LONGS=1
- Bull market (BTC > $108k): MACD hist > 0 → longs fire automatically

**To enable ASB1/HZBO1 longs when BTC goes bull:**
```bash
# Add to live env:
ASB1_ALLOW_LONGS=1
HZBO1_ALLOW_LONGS=1
# macro_require_bullish=True is default — no env change needed
# Longs will only fire when 4h MACD hist > 0
```

---

## Expected State After Launch

```
Alpaca intraday:  ✅ cron active, SPY gate checking every 5 min (market hours)
Alpaca monthly:   ✅ cron active, picks = NET/NFLX/XOM (April 2026 cycle)
Daily digest:     ✅ 08:00 UTC every day to Telegram
VOLADJ:           ✅ current BTC 4h ATR% ≈ 1.6% → mult=1.0 (no reduction needed)
ASB1/HZBO1 longs: ✅ macro-gated (safe to enable when bull market comes)
```

---

## Manual Test Commands

```bash
# Test intraday bridge (dry-run once):
bash scripts/run_equities_alpaca_intraday_dynamic_v1.sh --dry-run --once

# Test monthly bridge (dry-run):
ALPACA_SEND_ORDERS=0 python3 scripts/equities_alpaca_paper_bridge.py

# Send daily digest NOW:
python3 scripts/tg_daily_digest.py --dry-run   # print only
python3 scripts/tg_daily_digest.py              # send to TG

# Check current vol adjustment:
python3 -c "
import json
d = json.load(open('runtime/geometry/geometry_state.json'))
btc = d['symbols']['BTCUSDT']['240']
atr_pct = btc['atr'] / btc['current_price'] * 100
print(f'BTC 4h ATR%: {atr_pct:.2f}% (threshold=3.0%, current mult=1.0)')
"
```

---

Prepared by: Claude Sonnet 4.6 | 2026-04-17
