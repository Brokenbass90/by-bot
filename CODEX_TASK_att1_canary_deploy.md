# CODEX TASK: ATT1 Canary Deployment Verification

## Status: READY TO DEPLOY

The ATT1 integration into `smart_pump_reversal_bot.py` is complete.
The WF-22 verdict is in. This task covers server-side verification before go-live.

## Context

- ATT1 (`alt_trendline_touch_v1`): **🟢 DEPLOY** at 0.70× risk
  - WF-22 AvgPF=1.35, PF≥1.0: 55%, PF≥1.15: 45%
  - Recent 9 consecutive WF windows all PF>1.0
  - Risk mult reduced from initial 0.80 → 0.70 based on WF scatter
- ASM1 (`alt_sloped_momentum_v1`): **❌ DISABLED**
  - 0 trades in 10/22 WF windows; PF 0.44–0.70 in Jan–Feb 2026
  - Re-enable only when 3+ consecutive WF windows PF>1.2

Live config: `configs/core3_live_canary_20260411_sloped_momentum.env`

---

## Step 1 — Pull and verify on server

```bash
git pull origin codex/dynamic-symbol-filters
# or merge into main if ready

python3 -c "import smart_pump_reversal_bot; print('Import OK')"
grep -c "ENABLE_ATT1_TRADING\|try_att1_entry_async" smart_pump_reversal_bot.py
# Expected: >= 6
```

---

## Step 2 — Verify ATT1 strategy engine imports

```bash
python3 -c "
from strategies.att1_live import ATT1LiveEngine
print('ATT1LiveEngine OK')
" 2>&1
```

If this fails: check `strategies/att1_live.py` exists and imports cleanly.
The live engine wraps `AltTrendlineTouchV1Strategy` from `strategies/alt_trendline_touch_v1.py`.

---

## Step 3 — Run smoke tests

```bash
python3 tests/smoke_test.py
# Expected: ALL 10 TESTS PASSED
```

---

## Step 4 — Update live .env on server

Confirm `core3_live_canary_20260411_sloped_momentum.env` has:

```bash
# ATT1 — ENABLED at 0.70x risk (WF-22 validated)
ENABLE_ATT1_TRADING=1
ATT1_RISK_MULT=0.70
ATT1_MAX_OPEN_TRADES=2
ATT1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT

# ASM1 — DISABLED pending recovery
ENABLE_ASM1_TRADING=0
ASM1_RISK_MULT=0.0
```

---

## Step 5 — Canary restart

```bash
# Soft reload (if bot supports SIGHUP reload):
kill -HUP $(pgrep -f smart_pump_reversal_bot)

# Or full restart:
systemctl restart bybit-bot   # adjust to actual service name
```

---

## Step 6 — Monitor first 24 hours

Check logs for ATT1 signal activity:

```bash
grep "ATT1\|att1\|trendline_touch" /var/log/bybit-bot/bot.log | tail -50
```

Expected in first 24h on 8-symbol universe (50 trades/year ÷ 365 × 8 syms ≈ 1 signal/day):
- 0–2 ATT1 signals: **normal** (strategy is selective)
- 0 signals after 48h: check `ENABLE_ATT1_TRADING=1` and `ATT1_SYMBOL_ALLOWLIST` in live env

---

## Step 7 — Confirm health gate entry

`alt_trendline_touch_v1` must be in the health gate registry.
If you see `health_gate blocked att1` in logs, add an entry:

```json
{
  "strategy": "alt_trendline_touch_v1",
  "min_pf": 1.0,
  "lookback_days": 14,
  "min_trades": 3
}
```

---

## Known Issues / Notes

- **MIN_NOTIONAL_FILL_FRAC**: If running backtests for ATT1, set `MIN_NOTIONAL_FILL_FRAC=0`
  if ATR-based SL is tight relative to account equity. Default 0.40 can kill trades.
- **ATT1 timescale**: Uses 1h timeframe for pivot detection + 5m for entry bar.
  Ensure the live bot fetches both `"60"` and `"5"` intervals for ATT1 symbols.
- **ORCH_GLOBAL_RISK_MULT=0.50**: Config sets global risk halved — ATT1 effective risk
  is 0.50 × 0.70 = 0.35× baseline. This is intentional for canary.

---

## ASM1 Re-enablement Criteria

Re-enable ASM1 when the following conditions are met:
1. 3+ consecutive WF windows (45-day) each with PF≥1.2 on BTCUSDT+ETHUSDT
2. At least 30 total signals in those windows (not silence)
3. Drawdown in those windows ≤ 8%

When re-enabling: set `ENABLE_ASM1_TRADING=1`, `ASM1_RISK_MULT=0.60` (conservative start).

---

## Priority: HIGH (ATT1 is ready to generate live alpha)
## Estimated deploy time: 30 minutes
## Who: Server operator / Codex
