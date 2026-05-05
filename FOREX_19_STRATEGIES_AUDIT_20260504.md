# Forex Strategies Audit — 19 candidates → ranked top-5
**Дата:** 2026-05-04
**Автор:** Claude
**Цель:** оценить готовность для OANDA live deploy.

## Итог сразу

| Готовность | Кол-во |
|---|---:|
| ✅ Production-ready (можно live при наличии OANDA API) | 5 |
| 🟡 Нужна validation на годовом окне | 9 |
| 🔴 Прототип / archive | 5 |

## Top-5 для OANDA live (по убыванию приоритета)

### 1. `bb_mean_reversion_v3` ⭐⭐⭐⭐⭐
- **Зачем:** 4 версии (v1, v2, v2p, v3) = много iterations = зрелая логика
- **Где работает:** EURUSD, GBPUSD, USDJPY (range-bound majors)
- **Best regime:** asia/london overlap, EU midday (низкая vol = mean-reverting)
- **Risk:** низкий (BB bounds + tight SL)
- **Acceptance test:** annual EURUSD M5 > +200 pips, PF ≥ 1.4, DD ≤ 80 pips

### 2. `london_open_breakout_v2` ⭐⭐⭐⭐⭐
- **Зачем:** v2 имеет EMA trend filter (precomputed) — fast и точная
- **Где работает:** EURUSD, GBPUSD, EURJPY (London-active pairs)
- **Best regime:** **08:00-10:00 UTC** ровно (London open)
- **Risk:** средний (gap risk на news)
- **Acceptance test:** annual GBPUSD > +400 pips, PF ≥ 1.5, max single trade -50 pips

### 3. `trendline_break_bounce_v1` ⭐⭐⭐⭐
- **Зачем:** 348 строк = самая комплексная, прямой аналог ATT1 из crypto (главный двигатель canary v2)
- **Где работает:** все majors + EURJPY, GBPJPY (хорошие тренды)
- **Best regime:** trending sessions (london, NY)
- **Risk:** средний (trendline detection sensitivity)
- **Acceptance test:** мульти-pair sweep > +500 pips combined

### 4. `liquidity_sweep_bounce_session_v1` ⭐⭐⭐⭐
- **Зачем:** уже есть как forex-version моего crypto liquidity hunter
- **Где работает:** EURUSD, GBPUSD на London session
- **Best regime:** stop-hunt around session opens
- **Risk:** средний (false breakouts)
- **Acceptance test:** EURUSD annual > +250 pips на 50+ сделках

### 5. `ema_trend_pullback_v2` ⭐⭐⭐⭐
- **Зачем:** EMA pullback — классика, работает в форексе ВСЕГДА
- **Где работает:** USDJPY, GBPUSD trending pairs
- **Best regime:** strong trend (NY session afternoon)
- **Risk:** низкий-средний
- **Acceptance test:** USDJPY trending periods > +300 pips

---

## Tier 2 — нужна validation (9 стратегий)

| stratagy | Особенность | Action |
|---|---|---|
| `bb_mean_reversion_v1/v2/v2p` | Старые версии v3 | Сравнить с v3 — если v3 побеждает, archive |
| `breakout_continuation_session_v1` | Momentum continuation | Annual sweep на NY session |
| `failure_reclaim_session_v1` | False-break reclaim | Annual + WF |
| `range_bounce_session_v1` | Range bounce — primitive | Сравнить с bb_mean_reversion |
| `asia_range_reversion_session_v1` | Asia session специфично | Annual только Asia hours |
| `grid_reversion_session_v1` | Grid trading | RISKY, осторожно |
| `trend_retest_session_v1/v2` | Trend retest | v2 уже backtest'нут на equities (XOM, TSM) |
| `trend_pullback_rebound_v1` | Trend pullback | Backtest TSM показал +233 pips на 5 trades — слабая выборка |
| `adaptive_grid_range_v1` | Adaptive grid | Grid - всегда RISKY |

## Tier 3 — мусор / archive

- Старые v1 стратегии где есть v2/v3
- Grid стратегии без strict risk-management

## Что нужно для каждого OANDA live deploy

| Шаг | Кто | Время |
|---|---|---|
| 1. OANDA bridge code | Claude (готовлю сейчас) | 1 сессия |
| 2. OANDA API credentials | пользователь | через неделю |
| 3. Backtest top-5 на годовом окне | Codex | 2-3 часа CPU |
| 4. Paper account на OANDA | пользователь | 1 час |
| 5. Live shadow 7 дней | автомат | passive |
| 6. Real money $200 на топ-1 стратегии | пользователь approve | 1 час |
| 7. Расширение до top-5 после 30 дней live | Codex | 1 неделя |

## Реалистичная доходность OANDA

- v3 mean-reversion + london breakout combined → ~15-25% годовых на $1000
- На $500 (минимум для разумной диверсификации) → $75-150 чистого/год
- Не быстрее чем crypto, но **диверсифицирует портфолио** и **работает в часы когда крипта спит**

## Уникальное преимущество forex/CFD на OANDA

- Регуляция: OANDA US/EU regulated
- Низкий минимум: $0 для paper, $1 для real
- Низкий spread: EURUSD ~0.6 pips
- 24/5 (нет weekend gap)
- Можно plечо до 50:1 (не рекомендую больше 10:1)
- API REST + Streaming OK
