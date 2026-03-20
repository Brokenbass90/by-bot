# DeepSeek And Live Risk Plan 2026-03-19

## 1. DeepSeek staged integration

Goal: use a cheap LLM as an advisory/supervisory layer without letting it directly destabilize live trading.

### Phase 1: Post-trade advisor
- Trigger after each closed trade and once per day on the batch of closed trades.
- Inputs:
  - trade outcome
  - entry context
  - basic regime snapshot
  - news snapshot if available
- Outputs:
  - short explanation
  - candidate failure pattern
  - hypothesis for autoresearch
- Live impact:
  - none
- Why first:
  - safest layer
  - helps research immediately

### Phase 1a: Telegram advisory bootstrap
- Implemented local bootstrap path in code:
  - `bot/deepseek_overlay.py`
  - `/ai <question>` command in the main Telegram bot
  - `/ai_reset` to clear short chat history
- Current behavior:
  - read-only advisory mode only
  - uses local bot snapshot (`risk`, sleeves, diag counters, health summary, filter summary)
  - no trade execution, no parameter mutation
  - writes a simple audit trail of AI requests/replies for operator review
  - operator-side approval queue and budget guard are now scaffolded in Telegram
- Required env for activation:
  - `DEEPSEEK_ENABLE=1`
  - `DEEPSEEK_API_KEY=...`
  - optional: `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_TIMEOUT_SEC`
  - reference example: `configs/deepseek_overlay.env.example`
- Purpose:
  - give us a live conversational control surface before routing or execution overlays
  - keep the first integration safe and operator-facing

### Phase 2: Hourly regime supervisor
- Trigger hourly for crypto and daily or hourly for equities.
- Inputs:
  - BTC / ETH / SPY / QQQ / DXY snapshots
  - realized volatility
  - breadth / health score
  - macro/news digest
- Outputs:
  - `trend_up`, `trend_down`, `choppy`, `high_volatility`, `news_driven`
  - confidence
  - optional risk multiplier suggestion
- Live impact:
  - only sleeve enable/disable and risk haircut
- Fallback:
  - keep last valid regime for a bounded TTL

### Phase 3: News/context interpreter
- Trigger on event refresh or hourly.
- Inputs:
  - recent headlines
  - macro calendar items
  - affected assets
- Outputs:
  - `ignore`
  - `reduce_size`
  - `avoid`
  - time-based blackout hint
- Live impact:
  - context overlay only, not signal generation

### Phase 4: Signal router in shadow mode
- Trigger only when multiple sleeves compete on the same symbol.
- Inputs:
  - candidate signals
  - current regime
  - recent volatility/context
- Outputs:
  - selected signal
  - confidence
  - optional size multiplier
- Live impact:
  - shadow only at first
  - compare against current hard-priority router
- Current scaffold status:
  - local shadow journal path now exists in code
  - Telegram can inspect/reset recent shadow recommendations
  - advisory replies can already be mirrored into the shadow log for operator review
  - still missing: automatic capture of competing live sleeves and before/after outcome comparison

### Phase 5: Limited live routing
- Enable only after shadow logs show stable advantage.
- Still keep:
  - hard timeouts
  - safe fallback
  - deterministic default path when the API fails

## 2. Live crypto risk step-up

Current issue:
- with a small crypto account, `0.5%` risk per trade often produces notionals that are too small or hit min-qty friction
- jumping straight to `2.0%` per trade across several sleeves is too abrupt

### Step 1
- `RISK_PER_TRADE_PCT = 1.0`
- keep sleeve multipliers conservative
- keep `MAX_POSITIONS` unchanged
- observe for several days

### Step 2
- if min-qty friction is still common and live behavior remains clean:
- `RISK_PER_TRADE_PCT = 1.25`

### Step 3
- only after Step 2 is stable:
- `RISK_PER_TRADE_PCT = 1.5`

### Not recommended yet
- `2.0%` per trade on the whole live stack

## 3. Portfolio open-risk target

The code currently has:
- per-trade risk sizing
- daily loss limit
- max drawdown limit

It does not yet have a clean explicit cap on the sum of open stop-risk across all sleeves.

Recommended next implementation target:
- `MAX_OPEN_PORTFOLIO_RISK_PCT = 3.0` as first live version
- possible later increase to `3.5` after stable operation
- avoid jumping straight to `4-5%` total open risk until the weaker sleeves are better proven

## 4. Practical notes

- On a tiny account, larger stop distance naturally shrinks notional if position sizing is risk-based.
- More sleeves do not automatically mean more total risk if portfolio open-risk is capped.
- DeepSeek should start as a supervisor/advisor, not as a direct execution brain.
