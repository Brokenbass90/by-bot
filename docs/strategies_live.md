# Live Strategy Wiring (smart_pump_reversal_bot.py)

## Core Engines
- InPlayLiveEngine (inplay) controlled by ENABLE_INPLAY_TRADING
- BreakoutLiveEngine (inplay_breakout) controlled by ENABLE_BREAKOUT_TRADING
- RetestEngine (retest_levels) controlled by ENABLE_RETEST_TRADING
- RangeScanner/RangeStrategy controlled by ENABLE_RANGE_TRADING

## Bounce
- BounceStrategy is instantiated in smart_pump_reversal_bot.py
- Execution gated by BOUNCE_EXECUTE_TRADES
- Risk sizing uses RISK_PER_TRADE_PCT, MIN_NOTIONAL_USD, MIN_NOTIONAL_FILL_FRAC
- Many signals can be skipped if notional < min after sizing

## Pump-fade (original idea)
- Pump detection logic lives in smart_pump_reversal_bot.py
- Not controlled by an explicit ENABLE flag (uses pump logic paths)

## Where to Check Live Flags
- /root/by-bot/.env on the server
- Use: grep -E "ENABLE_|INPLAY_|BREAKOUT_|RETEST_|RANGE_|RISK_|CAP_|MAX_POSITIONS|MIN_NOTIONAL" /root/by-bot/.env
