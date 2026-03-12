# New Strategy Research Report — 2026-03-12

## Summary

This report covers research and backtesting of three new strategy directions:
1. **BB Mean Reversion V3** — advanced regime filter over V2
2. **Trendline Break & Bounce V1** — swing-pivot trendlines with 3rd-touch bounce
3. **LOB multi-pair expansion** — London Open Breakout on new pairs

Dataset: M5 candles ~Nov 2024 – Feb 2026 (~15–18 months depending on pair).
Spread: 1.2 pips. Swap: −0.2 pips/day. Risk: 1% per trade (pip estimates only).

---

## 1. Baseline: Proven Strategies

| Strategy | Pair | Trades | WR% | Net Pips | MaxDD | SumR | Assessment |
|----------|------|--------|-----|----------|-------|------|------------|
| LOB V1 (7-12 UTC) | EURUSD | 130 | 36.2 | **+374.6** | 630.7 | +12.5 | ✅ Primary |
| LOB V1 (7-12 UTC) | USDJPY | 36 | 41.7 | **+839.4** | 654.6 | +10.5 | ✅ Best pair |
| BB Mean Rev V2 | EURUSD | 85 | 48.2 | **+94.0** | 55.9 | +15.5 | ✅ Steady |

These three form the reliable core portfolio. Combined they offer ~1,300 pip potential across two pairs with low correlation (trend-following LOB + mean-reversion BB2).

---

## 2. LOB Multi-Pair Expansion

London Open Breakout V1 tested on all major pairs (session 07:00–12:00 UTC):

| Pair | Trades | WR% | Net Pips | SumR | Verdict |
|------|--------|-----|----------|------|---------|
| EURUSD | 130 | 36.2 | +374.6 | +12.5 | ✅ Deploy |
| USDJPY | 36 | 41.7 | +839.4 | +10.5 | ✅ Deploy |
| USDCHF | 28 | 32.1 | +48.0 | −0.9 | ⚠️ Marginal |
| AUDUSD | 6 | 50.0 | +113.4 | +3.3 | ⚠️ Too few trades |
| GBPUSD | 158 | 31.7 | −189.8 | −4.2 | ❌ Avoid |

**Why USDJPY works better than EURUSD:** JPY pairs have cleaner directional moves at London open due to carry-trade dynamics. The 41.7% win rate combined with ~2.0 average RR produces excellent expectancy. The risk is 3× wider SL in pips (~120 pips vs ~40), but lot-sizing adjusts for this automatically with 1% risk.

**Why GBPUSD underperforms:** GBP is more volatile at London open (domestic UK data releases, wider spread in practice). More fake breakouts. Avoid for now.

**Recommendation:** Run LOB V1 on EURUSD + USDJPY simultaneously. Combined expected: ~1,200 pips per 18 months, low overlap (different session dynamics).

---

## 3. BB Mean Reversion V3 — Result: Not Viable

### Goal
Improve V2 by adding:
- ADX proxy filter (block directional momentum)
- Body ratio confirmation (reject doji signals)

### Problem: Compound Filter Paradox

The compound filter creates a logical contradiction:

```
V2 regime: ATR < 90% of 50-bar avg   →  28.9% of bars pass
V3 adds: ADX < 28 (or 40)            →  down to 19.7% of bars
BB band width ≥ 20 pips              →  3.5% of bars
RSI at band extremes (< 40)          →  0.1% = 57 candidates
After cooldown + body filter + RR    →  4–6 trades total
```

The root cause: **when the market is genuinely ranging (ATR low + ADX low), price moves minimally and rarely reaches the BB bands**. The RSI only becomes extreme at the bands during moderate directional moves — exactly the bars ADX filters out.

This is an inherent paradox in combining "low-volatility regime" filters with "RSI at extreme bands" entry conditions.

### Results

| Config | Trades | WR% | Net Pips | SumR |
|--------|--------|-----|----------|------|
| V3 (RSI=40, ADX≤28) | 4 | 25.0 | −16.8 | −2.2 |
| V3 (RSI=40, ADX≤40) | 6 | 16.7 | −35.8 | −4.5 |

**Verdict: BB V3 in this form is not viable.** The ADX filter removes the very trades that make V2 work. V2 remains the better mean-reversion strategy.

### Path Forward for Future V3

Option A: Use Choppiness Index (CI > 58 = ranging) instead of ATR regime — CI works differently, detects *choppy* rather than *quiet* markets, and doesn't eliminate RSI extremes as aggressively.

Option B: Use ADX only to *confirm* trade direction (not as regime gate) — e.g., require ADX momentum to agree with RSI signal direction instead of blocking when ADX is high.

---

## 4. Trendline Break & Bounce V1 — Result: Bounces Fail, Breakouts Marginal

### Strategy Design

The strategy finds quality trendlines from swing pivots (N-bar local extremes), counts touches, and trades:
- **3rd-touch bounce**: price returns to tested trendline → reversal signal
- **Confirmed breakout**: price closes through trendline with RSI momentum

Trend alignment via SMA(1440) ensures bounces trade with the macro trend.

### EURUSD M5 Results

| Mode | Trades | WR% | Net Pips | SumR |
|------|--------|-----|----------|------|
| All signals | 369 | 27.9 | −593.4 | −300.8 |
| Bounces only | 124 | 19.4 | −115.8 | −266.3 |
| Breakouts only | 34 | 41.2 | −36.8 | −5.6 |

**Key finding:** The bounce signals are the problem (19.4% WR). Breakout signals are nearly break-even (41.2% WR, −5.6 SumR over 34 trades), suggesting real signal but insufficient edge on M5 data.

### Root Cause Analysis

The 3rd-touch bounce concept is well-established in technical analysis but functions on **higher timeframes** (H4, D1) where:
1. Swing pivots represent meaningful market structure (days/weeks of effort)
2. Each touch has been "tested" over a substantial period
3. Market memory is deeper → stronger reaction at the 3rd touch

On M5, with swing_window=5 (25-min pivots), the trendlines are:
- Formed from micro-structure that reverses quickly
- Touched many times per hour (noise rather than structure)
- Broken routinely without following through

The 28% WR (vs ~45% needed for breakeven at RR 1.3) confirms the M5 signal is essentially noise.

### Path Forward

**V2 Recommendation:** Implement a multi-timeframe approach:
1. Detect swing pivots on H1 candles (resample M5 → H1 in the strategy)
2. Draw trendlines on H1 structure
3. Execute on M5 for precise entry
4. This would mean each pivot is a 6-hour extreme rather than 25-minute

The infrastructure for pivot detection and touch counting is already solid. Only the timeframe data feeding needs to be upgraded.

**Near-term:** The trendline strategy is not ready for deployment. Archive as v1 (research), plan H1-detection V2.

---

## 5. Regime Indicators Library (forex/regime.py)

Three new indicators added to `forex/regime.py`:

| Indicator | Function | Range | Ranging signal |
|-----------|----------|-------|----------------|
| Choppiness Index | `choppiness(candles, i, period)` | 0–100 | > 61.8 |
| Volatility Percentile | `volatility_percentile(candles, i, ...)` | 0–100 | < 30 |
| ADX Proxy | `adx_proxy(candles, i, period)` | 0–100 | < 22 |
| Composite | `is_ranging(candles, i, ...)` | bool | 2-of-3 vote |

These are production-quality indicators, well-documented, and already used in BB V3.
Although V3 failed, the library is valuable for future strategies.

**EURUSD M5 calibration:**
- ADX proxy: median 29.6 (47% of bars below 28)
- CI: median 45.6 (only ~20% of bars above 61.8 = strongly ranging)

---

## 6. Overall Portfolio Recommendation

### Deploy Now

| Strategy | Pair | Expected | Notes |
|----------|------|----------|-------|
| LOB V1 | EURUSD | ~+370 pips/18mo | London session 07-12 UTC |
| LOB V1 | USDJPY | ~+840 pips/18mo | Best LOB pair, wider SL pips |
| BB Mean Rev V2 | EURUSD | ~+94 pips/18mo | Mean-reversion complement |

Total expected: ~1,300 pips / 18 months at 1% risk per trade.

### Do Not Deploy

- **BB V3**: compound filter paradox, too few trades
- **Trendline V1**: 28% WR (need 45%+), M5 bounces are noise
- **LOB on GBPUSD**: consistent losses, −190 pips

### Research Pipeline

1. **Trendline V2**: Multi-timeframe (H1 pivots + M5 execution) — highest priority for next research cycle
2. **BB V3 with CI regime**: Replace ATR regime filter with Choppiness Index as main gate
3. **LOB on AUDUSD**: Only 6 trades in this period; wait for more history before conclusion
4. **USDJPY BB V2**: Only 6 trades — USDJPY BB requires different parameter tuning for JPY volatility

---

## 7. Commit Contents

| File | Status | Description |
|------|--------|-------------|
| `forex/regime.py` | NEW | ChoppinessIndex, VolatilityPercentile, ADXProxy, is_ranging() |
| `forex/strategies/bb_mean_reversion_v3.py` | NEW | V3 with ADX + body filter (research only) |
| `forex/strategies/trendline_break_bounce_v1.py` | NEW | Trendline bounce/breakout V1 (research only) |
| `scripts/run_forex_backtest.py` | MODIFIED | Added V3, TLBB strategy registrations |
| `strategies/inplay_wrapper.py` | FIXED | try/except + warnings.warn for missing archive |
| `bot/symbol_state.py` | FIXED | stderr warning on indicators.py import failure |
