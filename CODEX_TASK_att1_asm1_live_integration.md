# CODEX TASK: Wire ATT1 + ASM1 into smart_pump_reversal_bot.py

## Context

Two new sloped strategies have been backtested, found profitable, and their live engine
wrappers have been written:

- `ATT1` (`alt_trendline_touch_v1`) — PF=1.263, 336 trades/year, DD=6.4%. 🟢 full risk
- `ASM1` (`alt_sloped_momentum_v1`) — PF=1.531, 171 trades/year, DD=4.6%. 🟢🟢 priority

Live engine wrappers: `strategies/att1_live.py`, `strategies/asm1_live.py`
Both follow the same pattern as `strategies/sloped_channel_live.py`.
Best params saved to: `configs/autoresearch/sloped_strategies_best_v1.json`

Health gate and dynamic_allowlist already updated (both entries added).

## What still needs to be done

Wire ATT1 and ASM1 into `smart_pump_reversal_bot.py`, following EXACTLY the pattern
used for sloped (ASC1) and flat (ARF1) strategies.

### Step 1 — Add global constants (near line 580-600)

Find the section where `SLOPED_ENGINE`, `FLAT_ENGINE` globals are declared.
Add analogous globals for ATT1 and ASM1:

```python
# ATT1 — swing-pivot trendline bounce
ATT1_ENGINE = None
ENABLE_ATT1_TRADING = os.getenv("ENABLE_ATT1_TRADING", "0").strip() == "1"
ATT1_RISK_MULT = float(os.getenv("ATT1_RISK_MULT", "1.0"))
ATT1_MAX_OPEN_TRADES = int(os.getenv("ATT1_MAX_OPEN_TRADES", "2"))
ATT1_TRY_EVERY_SEC = 60
ATT1_ALLOW_MINQTY_FALLBACK = True
ATT1_MINQTY_FALLBACK_MAX_MULT = 3.0
_ATT1_LAST_TRY: Dict[str, float] = {}

# ASM1 — sloped channel breakout momentum
ASM1_ENGINE = None
ENABLE_ASM1_TRADING = os.getenv("ENABLE_ASM1_TRADING", "0").strip() == "1"
ASM1_RISK_MULT = float(os.getenv("ASM1_RISK_MULT", "1.0"))
ASM1_MAX_OPEN_TRADES = int(os.getenv("ASM1_MAX_OPEN_TRADES", "2"))
ASM1_TRY_EVERY_SEC = 60
ASM1_ALLOW_MINQTY_FALLBACK = True
ASM1_MINQTY_FALLBACK_MAX_MULT = 3.0
_ASM1_LAST_TRY: Dict[str, float] = {}
```

### Step 2 — Add _ensure_att1_engine() and _ensure_asm1_engine() functions

Find `_ensure_sloped_engine()` and add analogous functions right after it:

```python
def _ensure_att1_engine() -> bool:
    global ATT1_ENGINE
    if ATT1_ENGINE is not None:
        return True
    try:
        from strategies.att1_live import ATT1LiveEngine
        ATT1_ENGINE = ATT1LiveEngine(fetch_klines)
        return True
    except Exception as e:
        log_error(f"_ensure_att1_engine failed: {e}")
        ATT1_ENGINE = None
        return False


def _ensure_asm1_engine() -> bool:
    global ASM1_ENGINE
    if ASM1_ENGINE is not None:
        return True
    try:
        from strategies.asm1_live import ASM1LiveEngine
        ASM1_ENGINE = ASM1LiveEngine(fetch_klines)
        return True
    except Exception as e:
        log_error(f"_ensure_asm1_engine failed: {e}")
        ASM1_ENGINE = None
        return False
```

### Step 3 — Add try_att1_entry_async() and try_asm1_entry_async()

Find `try_sloped_entry_async()` and add analogous functions right after it.
Copy the FULL body of `try_sloped_entry_async()` (lines ~7787-7935) and adapt:
- Replace `SLOPED_ENGINE` → `ATT1_ENGINE` (or `ASM1_ENGINE`)
- Replace `ENABLE_SLOPED_TRADING` → `ENABLE_ATT1_TRADING` (or `ENABLE_ASM1_TRADING`)
- Replace `SLOPED_MAX_OPEN_TRADES` → `ATT1_MAX_OPEN_TRADES`
- Replace `SLOPED_RISK_MULT` → `ATT1_RISK_MULT`
- Replace `SLOPED_ALLOW_MINQTY_FALLBACK` → `ATT1_ALLOW_MINQTY_FALLBACK`
- Replace `SLOPED_MINQTY_FALLBACK_MAX_MULT` → `ATT1_MINQTY_FALLBACK_MAX_MULT`
- Replace `_SLOPED_LAST_TRY` → `_ATT1_LAST_TRY`
- Replace `SLOPED_TRY_EVERY_SEC` → `ATT1_TRY_EVERY_SEC`
- Replace `tr.strategy = "sloped_channel"` → `tr.strategy = "att1_trendline_touch"`
- Replace the `_ensure_sloped_engine()` call → `_ensure_att1_engine()`
- Replace the `_health_gate.allow_entry("alt_sloped_channel_v1", ...)` check → `_health_gate.allow_entry("alt_trendline_touch_v1", ...)`
- Replace diagnostic keys: `sloped_` → `att1_`
- Replace `tg_trade("🟪 SLOPED ENTRY` → `tg_trade("🔷 ATT1 ENTRY`

Do the same for ASM1:
- `tr.strategy = "asm1_sloped_momentum"`
- `tg_trade("🟦 ASM1 ENTRY`
- Use `_health_gate.allow_entry("alt_sloped_momentum_v1", ...)`

### Step 4 — Add symbol allowlist loading

Find where `SLOPED_SYMBOL_ALLOWLIST` is loaded from env (around line 580-600 or in reload_config).
Add:
```python
ATT1_SYMBOL_ALLOWLIST = set(s.strip() for s in os.getenv("ATT1_SYMBOL_ALLOWLIST", "").split(",") if s.strip())
ASM1_SYMBOL_ALLOWLIST = set(s.strip() for s in os.getenv("ASM1_SYMBOL_ALLOWLIST", "").split(",") if s.strip())
```

Also add reload in `reload_config()`:
```python
global ATT1_SYMBOL_ALLOWLIST, ASM1_SYMBOL_ALLOWLIST
ATT1_SYMBOL_ALLOWLIST = set(s.strip() for s in os.getenv("ATT1_SYMBOL_ALLOWLIST", "").split(",") if s.strip())
ASM1_SYMBOL_ALLOWLIST = set(s.strip() for s in os.getenv("ASM1_SYMBOL_ALLOWLIST", "").split(",") if s.strip())
```

### Step 5 — Add dispatch to the main trading loop

Find the section (around line 9400-9420) where `try_sloped_entry_async` and `try_flat_entry_async` are dispatched:

```python
if ENABLE_SLOPED_TRADING and sym in SLOPED_SYMBOL_ALLOWLIST:
    asyncio.create_task(try_sloped_entry_async(sym, p1))
if ENABLE_FLAT_TRADING and sym in FLAT_SYMBOL_ALLOWLIST:
    asyncio.create_task(try_flat_entry_async(sym, p1))
```

Add after these blocks:
```python
if ENABLE_ATT1_TRADING and sym in ATT1_SYMBOL_ALLOWLIST:
    try:
        asyncio.create_task(try_att1_entry_async(sym, p1))
    except Exception as _e:
        log_error(f"try_att1_entry schedule fail {sym}: {_e}")

if ENABLE_ASM1_TRADING and sym in ASM1_SYMBOL_ALLOWLIST:
    try:
        asyncio.create_task(try_asm1_entry_async(sym, p1))
    except Exception as _e:
        log_error(f"try_asm1_entry schedule fail {sym}: {_e}")
```

### Step 6 — Update diagnostics/status reporting

Find where ENABLE_SLOPED_TRADING is reported in diagnostics (lines ~2390, ~2555, ~4006).
Add ATT1 and ASM1 to the same reporting lines.

Find where `"sloped": bool(ENABLE_SLOPED_TRADING)` appears and add:
```python
"att1": bool(ENABLE_ATT1_TRADING),
"asm1": bool(ENABLE_ASM1_TRADING),
```

### Step 7 — Update reload_config() and _rebuild_engines()

In `reload_config()` (around line 10133) and `_rebuild_engines()` (around line 10219),
add handling for ATT1 and ASM1 engines similar to how SLOPED_ENGINE is handled:
- Read `ENABLE_ATT1_TRADING` from env
- If disabled, set `ATT1_ENGINE = None`
- If enabled but engine is None, call `_ensure_att1_engine()`

## IMPORTANT: do NOT modify existing sloped (ASC1) code

The existing `try_sloped_entry_async` / `SLOPED_ENGINE` code must remain untouched.
ASC1 is currently disabled (ENABLE_SLOPED_TRADING=0) but the code must stay.
We are ADDING new entry functions, not replacing.

## Verification

After implementation:
1. `python3 -c "from strategies.att1_live import ATT1LiveEngine; print('ATT1 import OK')"` — must pass
2. `python3 -c "from strategies.asm1_live import ASM1LiveEngine; print('ASM1 import OK')"` — must pass
3. `grep -c "ENABLE_ATT1_TRADING\|ENABLE_ASM1_TRADING" smart_pump_reversal_bot.py` — should return ≥ 6
4. `python3 -c "import smart_pump_reversal_bot"` — must not raise ImportError

## Live config update

Add to `configs/core3_live_canary_20260411_sloped_momentum.env`:
```
ENABLE_ATT1_TRADING=1
ATT1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT
ATT1_RISK_MULT=0.80
ATT1_MAX_OPEN_TRADES=2
ATT1_PIVOT_LEFT=2
ATT1_PIVOT_RIGHT=2
ATT1_MIN_PIVOTS=2
ATT1_MAX_PIVOT_AGE=12
ATT1_MIN_R2=0.80
ATT1_TOUCH_ATR=0.25
ATT1_RSI_LONG_MAX=52
ATT1_RSI_SHORT_MIN=40

ENABLE_ASM1_TRADING=1
ASM1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT,XRPUSDT
ASM1_RISK_MULT=1.0
ASM1_MAX_OPEN_TRADES=2
ASM1_MIN_R2=0.25
ASM1_BREAKOUT_EXT_ATR=0.15
ASM1_MIN_BODY_FRAC=0.35
ASM1_VOL_MULT=2.0
ASM1_MIN_SLOPE_PCT=0.10
ASM1_USE_TREND_FILTER=0
```
