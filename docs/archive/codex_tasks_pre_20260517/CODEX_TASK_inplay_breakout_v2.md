# Codex Task: inplay_breakout_v2 — Modernised Breakout Strategy

## Why the old strategy died

`inplay_breakout` entered on the breakout bar itself (close > N-period high).
Modern market makers run price through obvious resistance to collect stops, then reverse.
Result: most entries were fake-breakouts hitting stop immediately.

## New approach — breakout_v2 with three extra guards

### Core logic change
Instead of entering ON the breakout bar, wait for:
1. **Impulse bar** — close above N-period high with volume spike (≥2× avg)  
2. **Consolidation** — price holds above the broken level for 2-4 bars without closing back below  
3. **Re-entry trigger** — a fresh bullish bar after consolidation (same as IVB1 retrace logic)

This filters 80% of fake-breakouts while keeping real ones.

### Parameters to implement (env-driven, same pattern as IVB1)

```python
BV2_LOOKBACK_BARS = 20         # N-period high lookback
BV2_BREAKOUT_BUFFER_ATR = 0.1  # buffer above the level (avoid noise)
BV2_MIN_VOL_MULT = 2.0         # impulse volume vs 20-bar avg
BV2_MIN_BODY_FRAC = 0.50       # impulse bar must be 50%+ body
BV2_HOLD_BARS_MIN = 2          # min bars holding above level before re-entry
BV2_HOLD_BARS_MAX = 6          # max bars waiting — if price goes back, abort
BV2_REENTRY_BODY_MIN = 0.40    # re-entry bar must be bullish with body
BV2_SL_ATR = 1.2               # stop below breakout level
BV2_RR = 1.8                   # R:R ratio
BV2_TP1_FRAC = 0.50            # partial exit at 1.0×R
BV2_TIME_STOP_BARS = 48        # abandon if no re-entry in 48 bars (4h)
BV2_COOLDOWN_BARS = 12
BV2_ALLOW_LONGS = 1
BV2_ALLOW_SHORTS = 0           # long-only by default (breakout in bear = risky)
BV2_SYMBOL_ALLOWLIST = ""      # empty = all symbols
BV2_REGIME_MODE = "ema"        # only trade in EMA21 > EMA55 (bull bias)
```

### State machine (3 states)

```
IDLE → [impulse detected] → ARMED → [consolidation confirmed] → WAITING_ENTRY
WAITING_ENTRY → [re-entry bar] → SIGNAL emitted → IDLE
WAITING_ENTRY → [price closes below level OR time exceeded] → IDLE (abort)
```

### File to create

`strategies/inplay_breakout_v2.py`

Pattern identical to `impulse_volume_breakout_v1.py`:
- `@dataclass class BreakoutV2Config`
- `class InplayBreakoutV2Strategy`
  - `STRATEGY_NAME = "inplay_breakout_v2"`
  - `maybe_signal(store, ts_ms, o, h, l, c, v) -> Optional[TradeSignal]`
  - Same regime filter pattern as IVB1 (`_regime_ok`)
  - Same cooldown/dedup as IVB1

### Backtest config to create

`configs/autoresearch/inplay_breakout_v2_current90_v1.json`

```json
{
  "name": "inplay_breakout_v2_current90_v1",
  "command": ["{python}", "backtest/run_portfolio.py",
    "--symbols", "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,TAOUSDT,HYPEUSDT,ADAUSDT,DOGEUSDT",
    "--strategies", "inplay_breakout_v2",
    "--days", "90",
    "--end", "2026-04-08",
    "--tag", "{tag}",
    "--starting_equity", "100",
    "--risk_pct", "0.01",
    "--leverage", "3",
    "--fee_bps", "6",
    "--slippage_bps", "2"
  ],
  "grid": {
    "BV2_LOOKBACK_BARS": [16, 20, 24],
    "BV2_MIN_VOL_MULT": [1.8, 2.2, 2.8],
    "BV2_HOLD_BARS_MIN": [2, 3],
    "BV2_HOLD_BARS_MAX": [5, 7],
    "BV2_SL_ATR": [1.0, 1.3, 1.6],
    "BV2_RR": [1.6, 2.0, 2.4]
  },
  "base_env": {
    "BV2_REGIME_MODE": "off",
    "BV2_ALLOW_LONGS": "1",
    "BV2_ALLOW_SHORTS": "0",
    "BV2_MIN_BODY_FRAC": "0.45",
    "BV2_COOLDOWN_BARS": "12",
    "BV2_TIME_STOP_BARS": "48",
    "BV2_BREAKOUT_BUFFER_ATR": "0.10"
  },
  "constraints": {
    "min_trades": 10,
    "min_profit_factor": 1.25,
    "max_drawdown": 10.0,
    "min_net_pnl": 2.0
  }
}
```

### After backtest

1. Compare best params vs IVB1 on the same 90d window — do they trade different setups or overlap?
2. If PF > 1.3 on current90: run on recent180 to confirm
3. If confirmed: add to allocator policy as `breakout_v2` sleeve (bull_trend only)
4. Add to `strategy_profile_registry.json`

### Success criteria

- At least 20 trades on current90
- PF ≥ 1.3, net ≥ 3%, DD ≤ 10%
- Less than 30% overlap with IVB1 signals (different setups)
