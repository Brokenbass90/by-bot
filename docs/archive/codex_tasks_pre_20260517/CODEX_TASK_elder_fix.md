# Codex Task: Fix Elder Triple Screen v2

## Problem Summary

`elder_triple_screen_v2.py` generates ~0 signals in live trading due to three configuration bugs.
No logic rewrite needed — only parameter fixes and one small Screen 3 tweak.

## File to Modify

`strategies/elder_triple_screen_v2.py`

---

## Fix 1: Loosen Screen 2 RSI thresholds (CRITICAL)

**Why**: `osc_os=35.0` requires 1H RSI(8) < 35 for a long in a bull trend.
In crypto, 4H uptrend + 1H RSI < 35 almost never coexist simultaneously.
1H RSI typically only reaches 40-48 during pullbacks in a real bull run.

**Change in `ElderTripleScreenV2Config`:**
```python
# Before:
osc_ob: float = 65.0
osc_os: float = 35.0

# After:
osc_ob: float = 58.0
osc_os: float = 42.0
```

Also update ENV defaults in the docstring:
```
ETS2_OSC_OB=58
ETS2_OSC_OS=42
```

---

## Fix 2: Extend Screen 3 retest window (HIGH)

**Why**: `entry_retest_bars=2` only looks 30 minutes back (2 × 15m bars).
A normal breakout-retest sequence takes 4-8 bars (1-2 hours).
Most valid setups are rejected because the touch happened 3+ bars ago.

**Change in `ElderTripleScreenV2Config`:**
```python
# Before:
entry_retest_bars: int = 2

# After:
entry_retest_bars: int = 5
```

---

## Fix 3: Shorten TP to reachable distance (HIGH)

**Why**: `tp_atr_mult=6.0` requires a ~$1200 move on 15m ATR basis for BTC.
This almost never gets filled. Add a two-TP structure instead.

**Change in `ElderTripleScreenV2Config`:**
```python
# Before:
tp_atr_mult: float = 6.0
trail_atr_mult: float = 1.5

# After:
tp_atr_mult: float = 2.5    # TP2 (full close)
tp1_atr_mult: float = 1.2   # TP1 (partial close, 50%)
tp1_frac: float = 0.50      # fraction closed at TP1
trail_atr_mult: float = 1.0  # tighter trail after TP1
```

**In `maybe_signal`, update the TradeSignal construction:**
```python
tp1 = entry_price + self.cfg.tp1_atr_mult * atr  # if long
tp2 = entry_price + self.cfg.tp_atr_mult * atr

sig = TradeSignal(
    strategy="elder_triple_screen_v2",
    symbol=store.symbol,
    side=side,
    entry=entry_price,
    sl=sl,
    tp=tp2,
    tps=[tp1, tp2],
    tp_fracs=[self.cfg.tp1_frac, 1.0 - self.cfg.tp1_frac],
    trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
    trailing_atr_period=14,
    time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
    reason=f"ets2_{trend}_{side}",
)
```
(Same pattern for short side with inverted arithmetic.)

---

## Fix 4: Remove daily signal throttle (MEDIUM)

**Why**: `max_signals_per_day=3` + `cooldown_bars_5m=60` (5 hours between signals)
means at most 3 trades per symbol per day. Combined with rare Screen 2 conditions,
this effectively kills the strategy. Remove the daily limit.

**Change in `ElderTripleScreenV2Config`:**
```python
# Before:
max_signals_per_day: int = 3
cooldown_bars_5m: int = 60

# After:
max_signals_per_day: int = 20    # effectively unlimited
cooldown_bars_5m: int = 18       # 90 minutes cooldown (reasonable)
```

---

## Fix 5: Add to portfolio_allocator_policy.json

Elder needs its own sleeve so the allocator can manage it by regime.
Elder is a trend-following strategy — enable in trend regimes, reduce in chop.

**Add to `configs/portfolio_allocator_policy.json` sleeves array:**
```json
{
  "name": "elder",
  "enable_env": "ENABLE_ELDER_TRADING",
  "symbol_env_key": "ETS2_SYMBOL_ALLOWLIST",
  "risk_env": "ELDER_RISK_MULT",
  "strategy_names": ["elder_triple_screen_v2"],
  "base_risk_mult_by_regime": {
    "bull_trend": 1.1,
    "bull_chop": 0.5,
    "bear_chop": 0.5,
    "bear_trend": 1.0
  }
}
```

---

## Fix 6: Wire Elder into smart_pump_reversal_bot.py

Same as IVB1 was wired in commits 494cb68/aecf792.
Search for where `ImpulseVolumeBreakoutV1Strategy` is imported and instantiated,
and add `ElderTripleScreenV2Strategy` in the same pattern.

Add to env config `configs/core3_impulse_candidate_20260408.env`:
```bash
ENABLE_ELDER_TRADING=1
ETS2_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT
ETS2_OSC_OS=42
ETS2_OSC_OB=58
ETS2_ENTRY_RETEST_BARS=5
ETS2_TP_ATR_MULT=2.5
ETS2_COOLDOWN_BARS_5M=18
ETS2_MAX_SIGNALS_PER_DAY=20
ELDER_RISK_MULT=1.0
```

---

## Backtest to Run After Fix

```json
{
  "name": "elder_fixed_current90_v1",
  "strategy": "elder_triple_screen_v2",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "days": 90,
  "env_overrides": {
    "ETS2_OSC_OS": "42",
    "ETS2_OSC_OB": "58",
    "ETS2_ENTRY_RETEST_BARS": "5",
    "ETS2_TP_ATR_MULT": "2.5",
    "ETS2_COOLDOWN_BARS_5M": "18",
    "ETS2_MAX_SIGNALS_PER_DAY": "20"
  }
}
```

Expected outcome: strategy should now generate 2-5 signals per symbol per week.

## Priority: HIGH
## Estimated effort: 2-3 hours
## Who: Codex
