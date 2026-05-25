# Codex Task: Scalper Architecture — Horizontal + Sloped, Longs + Shorts

## Vision

Add a family of 4 specialized scalpers controlled by the regime orchestrator.
Each scalper is a separate strategy class with its own env prefix, sleeve, and regime weights.
The orchestrator/allocator decides which ones are active based on regime — not the scalpers themselves.

---

## Architecture Overview

```
Orchestrator (regime) → Allocator (sleeve weights) → 4 Scalpers
                                                       ├── HorizLong  (HSLONG)
                                                       ├── HorizShort (HSSHORT)
                                                       ├── SlopedLong (SCLONG)
                                                       └── SlopedShort (SCSHORT)
```

Already existing: `micro_scalper_v1.py`, `micro_scalper_bounce_v1.py`, `alt_range_scalp_v1.py`
These are good bases. New scalpers will be CLEANER variants with explicit regime gating removed
(allocator handles regime, not the strategy).

---

## Scalper 1: Horizontal Support/Resistance Long (HSLONG)

**File**: `strategies/horiz_scalp_long_v1.py`  
**ENV prefix**: `HSL1_`  
**Concept**: Buy bounces off horizontal support levels on 15m  

**Entry logic:**
1. Detect support: lowest low over last `HSL1_LOOKBACK=20` bars on 15m
2. Price touches within `HSL1_TOUCH_ATR=0.3` ATR of support level
3. Close bar is bullish (close > open) with body ≥ 30% of range
4. RSI(14) on 15m between 30 and 55 (not overbought, mild pullback)
5. Volume: current bar ≥ `HSL1_VOL_MULT=1.0` × 20-bar avg

**Exit:**
- SL: support level − 0.8 ATR
- TP1: entry + 1.0 ATR (close 50%)
- TP2: entry + 2.5 ATR (close 50%)
- Time stop: 96 bars (8h on 5m polling)
- Cooldown: 12 bars (1h)

**Regime weight (in allocator policy):**
```json
"bull_trend": 1.2,
"bull_chop": 0.8,
"bear_chop": 0.3,
"bear_trend": 0.0
```

---

## Scalper 2: Horizontal Resistance Short (HSSHORT)

**File**: `strategies/horiz_scalp_short_v1.py`  
**ENV prefix**: `HSS1_`  
**Concept**: Short rejections off horizontal resistance on 15m  

**Entry logic:**
1. Detect resistance: highest high over last `HSS1_LOOKBACK=20` bars
2. Price touches within `HSS1_TOUCH_ATR=0.3` ATR of resistance
3. Close bar is bearish (close < open) with body ≥ 30% of range
4. RSI(14) on 15m between 45 and 70 (not oversold, mild bounce)
5. Volume: current bar ≥ `HSS1_VOL_MULT=1.0` × 20-bar avg

**Exit:**
- SL: resistance level + 0.8 ATR
- TP1: entry − 1.0 ATR (close 50%)
- TP2: entry − 2.5 ATR (close 50%)
- Time stop: 96 bars
- Cooldown: 12 bars

**Regime weight:**
```json
"bull_trend": 0.0,
"bull_chop": 0.6,
"bear_chop": 1.0,
"bear_trend": 1.2
```

---

## Scalper 3: Sloped Channel Long (SCLONG)

**File**: `strategies/sloped_scalp_long_v1.py`  
**ENV prefix**: `SCL1_`  
**Concept**: Buy touches of rising channel lower trendline on 1h  

**Entry logic:**
1. Compute linear regression slope over last `SCL1_REG_BARS=30` bars on 1h
2. Require slope > `SCL1_MIN_SLOPE_PCT=0.02` per bar (ascending channel)
3. Lower channel = regression − `SCL1_CHANNEL_ATR=1.5` ATR
4. Price touches lower channel within `SCL1_TOUCH_ATR=0.3` ATR
5. Entry on 15m close: bullish bar + RSI(14) 30-55

**Exit:**
- SL: lower_channel − 0.8 ATR
- TP1: midline of channel (close 40%)
- TP2: upper channel − 0.3 ATR (close 60%)
- Time stop: 144 bars
- Cooldown: 24 bars (2h)

**Regime weight:**
```json
"bull_trend": 1.3,
"bull_chop": 0.4,
"bear_chop": 0.0,
"bear_trend": 0.0
```

---

## Scalper 4: Sloped Channel Short (SCSHORT)

**File**: `strategies/sloped_scalp_short_v1.py`  
**ENV prefix**: `SCS1_`  
**Concept**: Short touches of falling channel upper trendline on 1h  

**Entry logic:**
1. Linear regression slope < `SCS1_MAX_SLOPE_PCT=-0.02` (descending channel)
2. Upper channel = regression + `SCS1_CHANNEL_ATR=1.5` ATR
3. Price touches upper channel within `SCS1_TOUCH_ATR=0.3` ATR
4. Entry on 15m: bearish bar + RSI(14) 45-70

**Exit:**
- SL: upper_channel + 0.8 ATR
- TP1: midline of channel (close 40%)
- TP2: lower channel + 0.3 ATR (close 60%)
- Time stop: 144 bars
- Cooldown: 24 bars

**Regime weight:**
```json
"bull_trend": 0.0,
"bull_chop": 0.3,
"bear_chop": 1.0,
"bear_trend": 1.3
```

---

## portfolio_allocator_policy.json additions

Add 4 new sleeves:

```json
{
  "name": "horiz_long",
  "enable_env": "ENABLE_HORIZ_LONG",
  "symbol_env_key": "HSL1_SYMBOL_ALLOWLIST",
  "risk_env": "HORIZ_LONG_RISK_MULT",
  "strategy_names": ["horiz_scalp_long_v1"],
  "base_risk_mult_by_regime": {
    "bull_trend": 1.2,
    "bull_chop": 0.8,
    "bear_chop": 0.3,
    "bear_trend": 0.0
  }
},
{
  "name": "horiz_short",
  "enable_env": "ENABLE_HORIZ_SHORT",
  "symbol_env_key": "HSS1_SYMBOL_ALLOWLIST",
  "risk_env": "HORIZ_SHORT_RISK_MULT",
  "strategy_names": ["horiz_scalp_short_v1"],
  "base_risk_mult_by_regime": {
    "bull_trend": 0.0,
    "bull_chop": 0.6,
    "bear_chop": 1.0,
    "bear_trend": 1.2
  }
},
{
  "name": "sloped_long",
  "enable_env": "ENABLE_SLOPED_LONG",
  "symbol_env_key": "SCL1_SYMBOL_ALLOWLIST",
  "risk_env": "SLOPED_LONG_RISK_MULT",
  "strategy_names": ["sloped_scalp_long_v1"],
  "base_risk_mult_by_regime": {
    "bull_trend": 1.3,
    "bull_chop": 0.4,
    "bear_chop": 0.0,
    "bear_trend": 0.0
  }
},
{
  "name": "sloped_short",
  "enable_env": "ENABLE_SLOPED_SHORT",
  "symbol_env_key": "SCS1_SYMBOL_ALLOWLIST",
  "risk_env": "SLOPED_SHORT_RISK_MULT",
  "strategy_names": ["sloped_scalp_short_v1"],
  "base_risk_mult_by_regime": {
    "bull_trend": 0.0,
    "bull_chop": 0.3,
    "bear_chop": 1.0,
    "bear_trend": 1.3
  }
}
```

---

## Implementation Order

1. **Phase 1** (start here): `horiz_scalp_long_v1.py` — simplest, pure horizontal SR
2. **Phase 2**: `horiz_scalp_short_v1.py` — mirror of Phase 1
3. **Phase 3**: Backtest both on current90 (90 days), validate signal count
4. **Phase 4**: `sloped_scalp_long_v1.py` + `sloped_scalp_short_v1.py` — add linear regression
5. **Phase 5**: Wire all 4 into live bot + allocator policy

## Naming Convention

Each strategy file must have at the module level:
```python
STRATEGY_NAME = "horiz_scalp_long_v1"  # matches policy JSON
```

## Priority: MEDIUM (after Elder fix and IVB1 validation)
## Estimated effort: 1-2 days total
## Who: Codex
