# Live Regime Orchestrator Spec

Date: 2026-04-02
Owner: GPT handoff for Codex
Status: implementation-ready spec

## Goal

Build a single live module that decides which strategy sleeves should be active in the current market regime.

This module is not a new trading strategy.
It is a portfolio-level controller that sits above existing strategies and reduces the current problem:

- all sleeves are always "on"
- each sleeve evaluates the market locally
- the bot has no shared opinion about regime
- long-biased sleeves keep firing in bad contexts

The orchestrator should turn the live bot from "a bag of independent strategies" into "a regime-aware portfolio".

## What the module must do

On a fixed schedule, compute a current market regime and write a small machine-readable state file/env overlay that the live bot can consume.

The regime layer must answer:

1. What regime are we in now?
2. Which sleeves should be enabled, reduced, or disabled?
3. What risk multiplier should apply globally?
4. Should the symbol universe be tightened?
5. Should long or short bias be preferred?

## Explicit non-goals

The first version must not:

- place trades itself
- rewrite strategy code
- auto-edit core `.env` blindly
- promote research candidates to live
- call external LLMs on every bar

Version 1 should be deterministic and rule-based.
AI can be added later as an advisory overlay, not as the first control layer.

## Existing sleeves the orchestrator must manage

### Momentum sleeve
- `inplay_breakout`
- `alt_inplay_breakdown_v1`
- `pump_momentum_v1`

### Mean-reversion / fade sleeve
- `alt_resistance_fade_v1`
- `pump_fade_v4r`

### Swing / geometry sleeve
- `btc_eth_midterm_pullback`
- `alt_sloped_channel_v1`

## Inputs

Version 1 should read only data already available in the codebase or easy to fetch locally.

### Market structure inputs
- BTCUSDT 4h OHLCV
- ETHUSDT 4h OHLCV
- BTCUSDT 1h OHLCV
- market breadth proxy from active universe:
  - fraction of symbols above EMA50/EMA200 on 1h or 4h
- optional BTC dominance proxy if already available cheaply

### Derived indicators
- EMA fast / slow on 4h
- ATR percentile
- Efficiency Ratio on 4h and 1h
- rolling return over:
  - 1 day
  - 3 days
  - 7 days
- realized volatility percentile

### Live health inputs
- last 20-50 closed trades from `trade_events` / `trades.db`
- per-sleeve rolling PnL
- per-sleeve hit rate
- per-sleeve stop-cluster count

## Output contract

The orchestrator should produce both:

1. JSON state file
2. env-style overlay file

Suggested paths:
- `runtime/regime/orchestrator_state.json`
- `configs/regime_orchestrator_latest.env`

### Minimum JSON schema

```json
{
  "timestamp_utc": "2026-04-02T12:00:00Z",
  "regime": "bearish_chop",
  "confidence": 0.78,
  "btc_bias": "short",
  "risk_level": 4,
  "global_risk_mult": 0.65,
  "sleeves": {
    "momentum": "reduced",
    "mean_reversion": "active",
    "swing": "active"
  },
  "strategy_overrides": {
    "ENABLE_BREAKOUT_TRADING": "0",
    "ENABLE_BREAKDOWN_TRADING": "1",
    "ENABLE_FLAT_TRADING": "1",
    "ENABLE_MIDTERM_TRADING": "1",
    "BREAKOUT_ALLOW_SHORTS": "1"
  },
  "symbol_bias": {
    "preferred": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "avoid": ["DOGEUSDT", "ADAUSDT"]
  },
  "notes": [
    "BTC 4h EMA21 below EMA55",
    "ER low on 4h, chop elevated",
    "recent long breakout sleeve underperforming"
  ]
}
```

### Minimum env overlay example

```bash
ORCH_REGIME=bearish_chop
ORCH_CONFIDENCE=0.78
ORCH_RISK_LEVEL=4
ORCH_GLOBAL_RISK_MULT=0.65
ENABLE_BREAKOUT_TRADING=0
ENABLE_BREAKDOWN_TRADING=1
ENABLE_FLAT_TRADING=1
ENABLE_MIDTERM_TRADING=1
BREAKOUT_ALLOW_SHORTS=1
```

## Required regime classes

Version 1 only needs 4 regimes:

1. `bull_trend`
2. `bull_chop`
3. `bear_chop`
4. `bear_trend`

This is enough to make live decisions without overcomplicating the first release.

## Decision logic

Use a simple scoring model, not a black box.

### Suggested regime rules

#### `bull_trend`
- BTC 4h EMA21 > EMA55
- BTC 4h close above EMA55
- 4h ER above threshold
- breadth positive

Action:
- momentum sleeve active
- swing sleeve active
- mean-reversion sleeve reduced or off

#### `bull_chop`
- BTC above EMA55, but ER low / choppy
- breadth mixed

Action:
- momentum reduced
- mean-reversion active
- swing reduced

#### `bear_chop`
- BTC 4h EMA21 < EMA55
- ER low
- breadth weak

Action:
- breakout longs off
- breakdown shorts on
- fade sleeve active
- swing sleeve selective only

#### `bear_trend`
- BTC 4h EMA21 < EMA55
- BTC below EMA55
- ER high enough to confirm trend
- breadth clearly weak

Action:
- breakdown sleeve active
- pump-fade active
- breakout longs off
- mean-reversion long logic off
- swing mostly reduced

## Sleeve control rules

The orchestrator should not tune everything.
It should only control:

- sleeve enable/disable
- sleeve risk multiplier
- optional directional permission
- optional allowlist narrowing

### Example actions by sleeve

#### `inplay_breakout`
- off in `bear_chop` and `bear_trend`
- on in `bull_trend`
- reduced in `bull_chop`

#### `alt_inplay_breakdown_v1`
- on in `bear_trend`
- reduced in `bear_chop`
- off in `bull_trend`

#### `alt_resistance_fade_v1`
- active only when chop is high
- off in strong trend regimes

#### `btc_eth_midterm_pullback`
- leave mostly independent
- only reduce risk in highest-risk regime

#### `alt_sloped_channel_v1`
- leave as low-frequency secondary sleeve
- do not make it a primary driver

## Risk policy

The orchestrator must expose a global risk multiplier.

Suggested mapping:
- `risk_level=1` -> `1.00`
- `risk_level=2` -> `0.85`
- `risk_level=3` -> `0.70`
- `risk_level=4` -> `0.50`

This multiplier should be applied on top of existing sleeve-level risk settings.

## Hysteresis (anti-flicker)

To prevent rapid regime oscillation at boundaries, a new regime is only
applied after **N consecutive cycles** agree on the new classification.

- Env var: `ORCH_MIN_HOLD_CYCLES` (default `3`)
- At 1-hour cadence this means a new regime takes ~3 hours to lock in
- The `pending_regime` and `pending_count` fields in the JSON state track this
- While waiting: the current applied regime stays in force
- On flip-flop: counter resets to 1 for the newest candidate

This prevents a boundary-sitting market from toggling overrides every hour.

## Scheduling

Version 1 cadence:
- compute regime every 1 hour
- recompute immediately on startup
- write JSON/env atomically

Cron entry (add to server crontab):
```
0 * * * * cd /root/by-bot && python3 scripts/build_regime_state.py >> logs/regime_orchestrator.log 2>&1
```

No per-bar decision loop is needed for version 1.

## Integration points

### New script
- `scripts/build_regime_state.py`

Responsibilities:
- load market data
- compute indicators
- classify regime
- emit JSON + env overlay

### Live bot integration
The live bot should:
- read `configs/regime_orchestrator_latest.env` on startup
- optionally reload every N minutes
- treat orchestrator overlay as highest-priority safe override layer

### Safety behavior
If the orchestrator output is missing, malformed, or stale:
- do not crash the bot
- fall back to current static config
- send a warning alert

## Observability

Must log:
- regime transitions
- reason for transition
- applied overrides
- sleeve toggles
- risk multiplier changes

Suggested log:
- `logs/regime_orchestrator.log`

Suggested Telegram alert on regime switch:
- concise summary only

Example:
- `Regime -> bear_chop | breakout OFF | breakdown ON | fade ON | risk x0.65`

## Acceptance criteria for version 1

Codex should consider V1 done when:

1. The regime script produces stable JSON/env output.
2. The output changes sensibly across historical bullish and bearish windows.
3. The live bot can consume the overlay without crashing.
4. Missing/stale orchestrator state fails safe.
5. A dry-run backtest or simulation can show that sleeve toggling changes behavior.

## Version 2 ideas

Only after V1 is stable:

- DeepSeek advisory overlay:
  - propose regime confidence adjustments
  - propose symbol preference lists
- nightly Claude/LLM scout:
  - write a structured market memo JSON
- portfolio health feedback:
  - reduce sleeves that are currently underperforming in live
- dynamic allowlist fusion:
  - combine regime bias with weekly allowlist research

## Recommended implementation order for Codex

1. Build deterministic regime classifier script.
2. Emit JSON + env overlay.
3. Add safe live-bot loader for the overlay.
4. Add logging and Telegram summary on regime change.
5. Add simple backtest/simulation harness for the regime layer.

## One-line summary

Build a deterministic portfolio-level regime controller that decides which sleeves are active, what risk multiplier applies, and whether the bot should lean long, short, or stay defensive.
